"""v2 research: does a 5-min burst have a forward edge in the INDEX itself (before any options)?

Pre-registered protocol (fixed before looking at results):
  * Split: TRAIN 2022-01-03..2024-06-30, TEST 2024-07-01..end. Configs are SELECTED on train only.
  * Signal: |m5| >= z_th * sigma5 (sigma5 = std of 5-min closes changes over the PRIOR 5 sessions -> no look-ahead).
    Only bars with a full 60-min lookback (bar start >= 10:15). Entry at that bar's close.
  * Burst direction b = sign(m5). Trade direction s = +b (continuation) or -b (fade).
  * Optional veto filters relative to b (mirroring v1 gate): trend60 == b ; 0.15 < rng < 0.85 ;
    b*m30 < 1.3*sigma5*sqrt(6) (exhaustion) ; bar start not in [12:00,13:00).
  * Non-overlapping: after a signal, further signals that day are ignored for h bars.
  * Outcome: s*(close[i+h]-close[i]) in units of sigma5*sqrt(h) ("sigma-h"), h in {3,6,12}; same-day, exit <= 15:15.
  * t-stat is DAY-CLUSTERED (signals within a day are not independent).
"""
from __future__ import annotations

import glob
import itertools
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent
SPLIT = pd.Timestamp("2024-07-01")
H_LIST = [3, 6, 12]


def load_index(sym: str) -> pd.DataFrame:
    rows = []
    for f in sorted(glob.glob(str(ROOT / "data/cache" / f"{sym}_*.csv"))):
        d = pd.read_csv(f, usecols=["ts", "open", "high", "low", "close"])
        if len(d) != 75:
            continue
        day = pd.Timestamp(os.path.basename(f)[len(sym) + 1:-4])
        c = d["close"].to_numpy(float)
        rec = pd.DataFrame({"date": day, "i": np.arange(75), "close": c, "high": d["high"].to_numpy(float),
                            "low": d["low"].to_numpy(float), "open": d["open"].to_numpy(float)})
        rows.append(rec)
    df = pd.concat(rows, ignore_index=True)
    g = df.groupby("date", sort=True)
    df["d5"] = g["close"].diff()
    # sigma5: prior-5-session pooled std of intraday 5-min changes (excludes today)
    var_by_day = g["d5"].apply(lambda s: np.nanmean(s.to_numpy() ** 2))
    sig = np.sqrt(var_by_day.rolling(5).mean().shift(1))
    df["sig"] = df["date"].map(sig)
    df["m5"] = g["close"].diff(1)
    df["m30"] = g["close"].diff(6)
    df["trend"] = np.sign(g["close"].diff(12))
    df["dhigh"] = g["high"].cummax()
    df["dlow"] = g["low"].cummin()
    span = (df["dhigh"] - df["dlow"]).replace(0, np.nan)
    df["rng"] = ((df["close"] - df["dlow"]) / span).fillna(0.5)
    for h in H_LIST:
        fwd = g["close"].shift(-h) - df["close"]
        fwd[df["i"] + h > 72] = np.nan                     # exit must be at/before 15:15
        df[f"fwd{h}"] = fwd
    for h in H_LIST:   # adverse/favourable extremes over the NEXT h bars (for stop checks in the option sim)
        lows = [g["low"].shift(-k) for k in range(1, h + 1)]
        highs = [g["high"].shift(-k) for k in range(1, h + 1)]
        df[f"lowmin{h}"] = np.fmin.reduce([x.to_numpy() for x in lows])
        df[f"highmax{h}"] = np.fmax.reduce([x.to_numpy() for x in highs])
    df = df.dropna(subset=["sig", "m5", "m30", "trend"]).reset_index(drop=True)
    return df


def signals(df: pd.DataFrame, cfg: dict, h: int) -> pd.DataFrame:
    """Apply a config, then enforce non-overlap (refractory h bars per day)."""
    z = df["m5"] / df["sig"]
    b = np.sign(df["m5"])
    m = (z.abs() >= cfg["z"]) & df[f"fwd{h}"].notna()
    if cfg["trend"]:
        m &= df["trend"] == b
    if cfg["rng"]:
        m &= (df["rng"] > 0.15) & (df["rng"] < 0.85)
    if cfg["exh"]:
        m &= (b * df["m30"]) < 1.3 * df["sig"] * np.sqrt(6)
    if cfg["mid"]:
        m &= ~((df["i"] >= 33) & (df["i"] <= 44))          # bar start in [12:00, 13:00)
    s = df[m].copy()
    s["b"] = b[m]
    s["side"] = s["b"] * (1 if cfg["dir"] == "cont" else -1)
    keep, last_day, last_i = [], None, -99
    for idx, r in zip(s.index, s[["date", "i"]].itertuples(index=False)):
        if r.date != last_day:
            last_day, last_i = r.date, -99
        if r.i >= last_i + h:                                # non-overlapping
            keep.append(idx)
            last_i = r.i
    s = s.loc[keep]
    s["pts"] = s["side"] * s[f"fwd{h}"]
    s["u"] = s["pts"] / (s["sig"] * np.sqrt(h))              # sigma-h units
    return s


def stats(s: pd.DataFrame) -> dict:
    n = len(s)
    if n < 30:
        return dict(n=n, mean_u=np.nan, t=np.nan, pts=np.nan, hit=np.nan, days=s["date"].nunique())
    mu = s["u"].mean()
    dev = s.groupby("date")["u"].apply(lambda x: (x - mu).sum())     # cluster-robust SE of the mean
    se = np.sqrt((dev**2).sum()) / n
    return dict(n=n, mean_u=mu, t=mu / se if se > 0 else np.nan, pts=s["pts"].mean(),
                hit=(s["u"] > 0).mean(), days=s["date"].nunique())


def grid():
    for d, z, tr, rg, ex, md in itertools.product(["cont", "fade"], [2.0, 3.0], [0, 1], [0, 1], [0, 1], [0, 1]):
        yield dict(dir=d, z=z, trend=tr, rng=rg, exh=ex, mid=md)


def label(c: dict) -> str:
    f = "".join(k[0].upper() for k in ("trend", "rng", "exh", "mid") if c[k]) or "-"
    return f"{c['dir']}|z{c['z']:.0f}|{f}"


def main() -> None:
    out_rows = []
    for sym in ("NIFTY", "SENSEX"):
        df = load_index(sym)
        tr, te = df[df["date"] < SPLIT], df[df["date"] >= SPLIT]
        print(f"{sym}: {df['date'].nunique()} days; train {tr['date'].nunique()}, test {te['date'].nunique()}; "
              f"median sigma5 train {tr['sig'].median():.1f} pts, test {te['sig'].median():.1f} pts")
        for h in H_LIST:
            for c in grid():
                a, b_ = stats(signals(tr, c, h)), stats(signals(te, c, h))
                out_rows.append(dict(index=sym, h=h, cfg=label(c), **c, **{f"tr_{k}": v for k, v in a.items()},
                                     **{f"te_{k}": v for k, v in b_.items()}))
    res = pd.DataFrame(out_rows)
    res.to_csv(ROOT / "versions/v2/results/edge_study_all_configs.csv", index=False)
    pd.set_option("display.width", 220)
    cols = ["index", "h", "cfg", "tr_n", "tr_mean_u", "tr_t", "te_n", "te_mean_u", "te_t", "te_pts"]
    print("\nBaseline sanity — if signals were pure noise we'd expect |t| < 2 for ~95% of the 64 configs per (index,h).")
    for (ix, h), g in res.groupby(["index", "h"]):
        print(f"  {ix} h={h:>2}: train |t|>2 in {(g.tr_t.abs() > 2).sum()}/64, test |t|>2 in {(g.te_t.abs() > 2).sum()}/64; "
              f"corr(train t, test t)={g[['tr_t','te_t']].corr().iloc[0,1]:.2f}")
    print("\nTOP 8 by TRAIN t-stat per (index, h) with their TEST outcome (selection on train only):")
    for (ix, h), g in res.groupby(["index", "h"]):
        print(f"\n-- {ix} h={h} ({h*5} min)")
        print(g.sort_values("tr_t", ascending=False).head(8)[cols].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
