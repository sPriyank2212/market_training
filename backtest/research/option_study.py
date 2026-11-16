"""v2 research, layer B: turn the index-level edge into COSTED option P&L (long ATM CE/PE, time exit).

Model (all assumptions explicit, none tuned on TEST):
  * Contract: ATM (nearest strike step), constant-maturity Black-Scholes with DTE calendar days at entry
    (expiry calendars changed several times 2022-26, so a fixed DTE is used instead of a schedule), flat IV.
  * Entry at the signal bar's close, exit at close of bar i+h (time exit), hard stop if premium touches -15%
    (stop fills at the level, SL-first). Theta emerges from T shrinking.
  * Costs: slippage per side (% of premium) + brokerage (flat/order + GST) + STT on sell + exchange + stamp.
  * Selection on TRAIN only; TEST evaluated once for the selected configs. Results in % of premium per trade
    (lot sizes changed over the period) with day-clustered t-stats, plus an illustrative rupee total at a fixed lot.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))
import edge_study as ES
from premium import bs_price

STEP = {"NIFTY": 50, "SENSEX": 100}
LOT = {"NIFTY": 65, "SENSEX": 20}                    # illustrative fixed lot for the rupee column only
COST = dict(slip={"NIFTY": 0.003, "SENSEX": 0.006},  # per side, fraction of premium
            brokerage=20.0, gst=0.18, stt_sell=0.001, exch=0.00035, stamp_buy=0.00003, sebi=1e-6)
MODEL = dict(dte=4.0, iv={"NIFTY": 0.12, "SENSEX": 0.13}, r=0.065, stop=0.15)


def simulate(s: pd.DataFrame, sym: str, h: int, cost_mult: float = 1.0, dte: float | None = None,
             iv: float | None = None) -> pd.DataFrame:
    """s: signals from ES.signals (has side, close, fwd{h}, lowmin{h}, highmax{h})."""
    dte = MODEL["dte"] if dte is None else dte
    iv = MODEL["iv"][sym] if iv is None else iv
    S0 = s["close"].to_numpy(float)
    side = s["side"].to_numpy(float)
    K = np.round(S0 / STEP[sym]) * STEP[sym]
    T0 = dte / 365.0
    T1 = T0 - (h * 5) / (365.0 * 24 * 60)
    S1 = S0 + s[f"fwd{h}"].to_numpy(float)
    # adverse extreme for the position: CE hurt by lows, PE hurt by highs
    Sadv = np.where(side > 0, s[f"lowmin{h}"].to_numpy(float), s[f"highmax{h}"].to_numpy(float))

    def px(S):
        return np.where(side > 0, bs_price(S, K, T1, MODEL["r"], iv, True), bs_price(S, K, T1, MODEL["r"], iv, False))

    P0 = np.where(side > 0, bs_price(S0, K, T0, MODEL["r"], iv, True), bs_price(S0, K, T0, MODEL["r"], iv, False))
    P1, Padv = px(S1), px(Sadv)
    stopped = Padv <= P0 * (1 - MODEL["stop"])
    Pexit = np.where(stopped, P0 * (1 - MODEL["stop"]), P1)
    slip = COST["slip"][sym] * cost_mult
    units = LOT[sym]
    buy, sell = P0 * (1 + slip), Pexit * (1 - slip)
    n_in, n_out = buy * units, sell * units
    fees = cost_mult * (2 * COST["brokerage"] * (1 + COST["gst"]) + COST["stt_sell"] * n_out
                        + COST["exch"] * (n_in + n_out) + COST["stamp_buy"] * n_in + COST["sebi"] * (n_in + n_out))
    net = units * (sell - buy) - fees
    out = s[["date"]].copy()
    out["ret"] = net / (P0 * units)                      # return on premium paid, net of all costs
    out["gross_ret"] = (Pexit - P0) / P0
    out["rupees"] = net
    out["stopped"] = stopped
    out["P0"] = P0
    return out


def summarize(o: pd.DataFrame) -> dict:
    n = len(o)
    if n < 30:
        return dict(n=n, net=np.nan, t=np.nan, gross=np.nan, win=np.nan, rs_total=np.nan, days=o["date"].nunique(), dd=np.nan)
    mu = o["ret"].mean()
    dev = o.groupby("date")["ret"].apply(lambda x: (x - mu).sum())
    se = np.sqrt((dev**2).sum()) / n
    daily = o.groupby("date")["rupees"].sum()
    eq = daily.cumsum()
    return dict(n=n, net=mu, t=mu / se, gross=o["gross_ret"].mean(), win=(o["ret"] > 0).mean(),
                rs_total=o["rupees"].sum(), days=o["date"].nunique(), dd=(eq - eq.cummax()).min())


def main() -> None:
    allrows, picks = [], []
    data = {sym: ES.load_index(sym) for sym in ("NIFTY", "SENSEX")}
    for sym, df in data.items():
        tr, te = df[df["date"] < ES.SPLIT], df[df["date"] >= ES.SPLIT]
        for h in (3, 6):
            for c in ES.grid():
                a = summarize(simulate(ES.signals(tr, c, h), sym, h)) if len(ES.signals(tr, c, h)) else {}
                b = summarize(simulate(ES.signals(te, c, h), sym, h)) if len(ES.signals(te, c, h)) else {}
                allrows.append(dict(index=sym, h=h, cfg=ES.label(c), **c, **{f"tr_{k}": v for k, v in a.items()},
                                    **{f"te_{k}": v for k, v in b.items()}))
    res = pd.DataFrame(allrows)
    res.to_csv(ES.ROOT / "versions/v2/results/option_study_all_configs.csv", index=False)
    pd.set_option("display.width", 230)
    cols = ["index", "h", "cfg", "tr_n", "tr_gross", "tr_net", "tr_t", "te_n", "te_gross", "te_net", "te_t", "te_win", "te_rs_total", "te_dd"]
    pct = lambda d: d.assign(**{c: (d[c] * 100).round(2) for c in d.columns if c.endswith(("gross", "net", "win"))})
    print("Fraction of configs net-positive:  TRAIN %.0f%%  TEST %.0f%%   (all 64x2 h x 2 indices)" %
          (100 * (res.tr_net > 0).mean(), 100 * (res.te_net > 0).mean()))
    sel = res[(res.tr_n >= 250) & (res.tr_t >= 2.0)].sort_values("tr_t", ascending=False)
    print("\nPRE-SET SELECTION RULE: train n>=250 and train net-return t>=2; ranked by train t. TEST outcome shown (returns in % of premium):")
    print(pct(sel.head(12)[cols]).round(2).to_string(index=False) if len(sel) else "  (no config passes the train rule)")
    print("\nTop 10 by TRAIN net t regardless of rule (for context):")
    print(pct(res.sort_values("tr_t", ascending=False).head(10)[cols]).round(2).to_string(index=False))


if __name__ == "__main__":
    main()
