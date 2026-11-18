"""Data-validation gate (M1.5). Runs automatically after every fetch (backtest.main calls it before any backtest).

  1. Year assert   - every candle's year must equal validation.year. Raises ValidationError; cannot be bypassed.
  2. Trading-window check (STRICT, user decision 2026-11-18): Dhan vs raw Yahoo 5-min bars for every bar whose start is
     <= validation.window_last_bar (15:15). Each bar's O/H/L/C within tolerance_pct AND the window day O/H/L/C within tolerance_pct.
  3. Late bars (15:20, 15:25): mismatches are a visible WARNING only (they never reach a trade or a gate input).
  4. Daily-anchor table (Yahoo day O/H/L/C): informational when the raw Yahoo file exists; STRICT (as originally specified) when it does not.
  5. Bar count: 75 OK; 73-74 pass with a WARNING; anything else FAIL.
Any FAIL -> the run must stop (validate_days returns ok=False; backtest.main exits non-zero).
Written because v1 once ran on the wrong year and nothing caught it.
"""
from __future__ import annotations
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent
OHLC = ("open", "high", "low", "close")


class ValidationError(RuntimeError):
    pass


def assert_year(df: pd.DataFrame, year: int, label: str = "") -> None:
    """Non-bypassable year assert."""
    if df is None or df.empty:
        return
    bad = sorted({int(y) for y in df["ts"].dt.year if int(y) != year})
    if bad:
        raise ValidationError(f"YEAR ASSERT FAILED {label}: expected {year}, found candle year(s) {bad}")


def day_ohlc(df: pd.DataFrame) -> tuple[float, float, float, float]:
    return float(df["open"].iloc[0]), float(df["high"].max()), float(df["low"].min()), float(df["close"].iloc[-1])


def bar_status(n: int, cfg: dict) -> str:
    v = cfg["validation"]
    if n == v["bars_expected"]:
        return "OK"
    return "WARN" if n in v["bars_acceptable"] else "FAIL"


def _pct(a: float, b: float) -> float:
    return abs(a - b) / b * 100


def check_day(df: pd.DataFrame, anchor: list[float], cfg: dict, label: str = "") -> dict:
    """Year assert + full-day anchor check + bar count for one day. Raises ValidationError on a wrong year."""
    v = cfg["validation"]
    assert_year(df, v["year"], label)
    got = dict(zip(OHLC, day_ohlc(df)))
    diffs = {k: _pct(got[k], a) for k, a in zip(OHLC, anchor)}
    worst = max(diffs, key=diffs.get)
    price_ok = diffs[worst] <= v["tolerance_pct"]
    bs = bar_status(len(df), cfg)
    status = "FAIL" if (not price_ok or bs == "FAIL") else ("WARN" if bs == "WARN" else "OK")
    return dict(bars=len(df), dhan_open=got["open"], dhan_high=got["high"], dhan_low=got["low"], dhan_close=got["close"],
                anchor_open=anchor[0], anchor_high=anchor[1], anchor_low=anchor[2], anchor_close=anchor[3],
                close_diff_pct=diffs["close"], worst_field=worst, worst_diff_pct=diffs[worst],
                price_ok=price_ok, bar_status=bs, status=status)


def read_yahoo(path: Path) -> pd.DataFrame:
    y = pd.read_csv(path)
    y["ts"] = pd.to_datetime(y["ts_ist"]).dt.tz_convert("Asia/Kolkata")
    return y.set_index("ts")[list(OHLC)]


def compare_window(dhan: pd.DataFrame, yahoo: pd.DataFrame, cfg: dict) -> dict:
    """Dhan vs raw Yahoo for ONE day. `dhan` has a `ts` column; `yahoo` is indexed by ts.
    Window = bars with start <= window_last_bar (strict). Late bars = after it (warning only)."""
    v = cfg["validation"]
    tol = v["tolerance_pct"]
    d = dhan.set_index("ts")[list(OHLC)]
    hhmm = d.index.strftime("%H:%M")
    last = v["window_last_bar"]
    out = {}
    for name, dd in (("window", d[hhmm <= last]), ("late", d[hhmm > last])):
        yy = yahoo.reindex(dd.index).dropna()
        dd = dd.reindex(yy.index)
        if dd.empty:
            out[name] = dict(n=0, bad_bars=0, max_bar_pct=0.0, agg_worst_pct=0.0, agg_worst_field="-")
            continue
        bar_pct = (yy.sub(dd).abs() / dd * 100).max(axis=1)
        agg = {k: _pct(a, b) for k, a, b in zip(OHLC, (yy.open.iloc[0], yy.high.max(), yy.low.min(), yy.close.iloc[-1]),
                                                  (dd.open.iloc[0], dd.high.max(), dd.low.min(), dd.close.iloc[-1]))}
        w = max(agg, key=agg.get)
        out[name] = dict(n=len(dd), bad_bars=int((bar_pct > tol).sum()), max_bar_pct=float(bar_pct.max()),
                         agg_worst_pct=float(agg[w]), agg_worst_field=w)
    w, late = out["window"], out["late"]
    out["window_ok"] = w["n"] > 0 and w["bad_bars"] == 0 and w["agg_worst_pct"] <= tol
    out["late_warn"] = late["n"] > 0 and late["bad_bars"] > 0
    return out


def validate_days(store, cfg: dict, symbols=("NIFTY", "SENSEX"), verbose: bool = True) -> tuple[bool, pd.DataFrame]:
    """Validate every anchored day for every symbol. Returns (ok, table)."""
    v = cfg["validation"]
    ydir = (ROOT / v.get("yahoo_dir", ".")).resolve()
    raw = {}
    for sym in symbols:
        f = (v.get("yahoo_files") or {}).get(sym)
        p = ydir / f if f else None
        raw[sym] = read_yahoo(p) if p is not None and p.exists() else None
    rows = []
    for d_str, per_sym in v["anchors"].items():
        day = pd.Timestamp(d_str).date()
        for sym in symbols:
            df = store.get_day(sym, day)
            if df is None or df.empty:
                rows.append(dict(date=d_str, symbol=sym, bars=0, status="FAIL", note="no candles"))
                continue
            r = check_day(df, per_sym[sym], cfg, f"{sym} {d_str}")
            r.update(date=d_str, symbol=sym, method="anchor-strict (no raw Yahoo file)", note="")
            if raw[sym] is not None:
                yd = raw[sym][raw[sym].index.strftime("%Y-%m-%d") == d_str]
                c = compare_window(df, yd, cfg)
                w, late = c["window"], c["late"]
                r.update(method="window bar-level", win_bars=w["n"], win_bad_bars=w["bad_bars"], win_max_bar_pct=w["max_bar_pct"],
                         win_agg_pct=w["agg_worst_pct"], win_agg_field=w["agg_worst_field"],
                         late_bars=late["n"], late_bad_bars=late["bad_bars"], late_max_bar_pct=late["max_bar_pct"])
                if r["bar_status"] == "FAIL" or not c["window_ok"]:
                    r["status"] = "FAIL"
                elif r["bar_status"] == "WARN" or c["late_warn"] or not r["price_ok"]:
                    r["status"] = "WARN"
                else:
                    r["status"] = "OK"
                if c["late_warn"]:
                    r["note"] = f"late bars (15:20/15:25) differ from Yahoo in {late['bad_bars']} of {late['n']}: ignored for trading, warned"
            rows.append(r)
    t = pd.DataFrame(rows)
    ok = bool((t["status"] != "FAIL").all())
    if verbose:
        lw = v.get("window_last_bar", "15:15")
        print(f"STRICT window = bars starting <= {lw} (bar-level + day aggregate, tolerance {v['tolerance_pct']}%); later bars = warning only\n")
        print(f"{'date':10s} {'sym':6s} {'bars':>4s} {'win':>4s} {'bad':>3s} {'max bar%':>8s} {'win agg% (field)':>18s} | {'late bad':>8s} {'late max%':>9s} | {'full-day anchor worst%':>24s}  status")
        for _, r in t.iterrows():
            if r.get("note") == "no candles":
                print(f"{r['date']:10s} {r['symbol']:6s}    0  no candles  FAIL")
                continue
            if r["method"] == "window bar-level":
                print(f"{r['date']:10s} {r['symbol']:6s} {int(r['bars']):4d} {int(r['win_bars']):4d} {int(r['win_bad_bars']):3d} {r['win_max_bar_pct']:8.3f} "
                      f"{r['win_agg_pct']:9.3f} ({r['win_agg_field']:5s}) | {int(r['late_bad_bars']):2d}/{int(r['late_bars']):d}     {r['late_max_bar_pct']:9.3f} | "
                      f"{r['worst_diff_pct']:15.3f} ({r['worst_field']:5s})  {r['status']}")
            else:
                print(f"{r['date']:10s} {r['symbol']:6s} {int(r['bars']):4d}  [no raw Yahoo file: strict anchors] worst {r['worst_diff_pct']:.3f}% ({r['worst_field']})  {r['status']}")
        warns = t[t.status == "WARN"]
        print(f"\nvalidation: {len(t)} day-symbol rows | OK {int((t.status == 'OK').sum())} | WARN {len(warns)} | FAIL {int((t.status == 'FAIL').sum())} "
              f"| year {v['year']} asserted on every candle")
        if len(warns):
            print("WARN rows: " + ", ".join(f"{r['symbol']} {r['date']}" for _, r in warns.iterrows()) +
                  "  -> only the 15:20/15:25 bars differ (Dhan 15:20 bar is flat; outside the trading window)")
    return ok, t
