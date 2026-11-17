"""Load + clean signals; load cached spot / option candles. Split and exclusions follow PLAN.md."""
from __future__ import annotations
from common import *

STEP = {"NIFTY": 50, "SENSEX": 100}
VALID_DAYS = {"2026-10-23", "2026-10-30", "2026-11-05", "2026-11-13"}   # fixed in PLAN.md

def spot(sym: str, day) -> pd.DataFrame:
    p = CACHE / f"spot_{sym}_{day}.csv"
    if not p.exists(): return pd.DataFrame()
    df = pd.read_csv(p)
    if df.empty: return df
    df["ts"] = pd.to_datetime(df["ts"]); return df.set_index("ts")

def spot_all(sym: str, days) -> pd.DataFrame:
    return pd.concat([spot(sym, d).assign(day=str(d)) for d in days if len(spot(sym, d))])

def option(sym, day, code, side, k) -> pd.DataFrame:
    p = CACHE / f"opt_{sym}_{day}_c{code}_{side}_k{k:+d}.csv"
    if not p.exists(): return pd.DataFrame()
    df = pd.read_csv(p)
    if df.empty: return df
    df["ts"] = pd.to_datetime(df["ts"]); return df.set_index("ts")

def signals() -> pd.DataFrame:
    d = pd.read_excel(SIGNALS_XLSX)
    d = d.rename(columns={"Index": "idx", "Entry Premium": "entry", "Exit Premium": "exit", "Target 1": "t1",
                          "Target 2": "t2", "Premium SL": "sl", "Expiry": "expiry", "Lot": "lot",
                          "P&L (Rs)": "pnl", "P&L (%)": "pnl_pct", "Status": "status", "Notes": "notes"})
    d["row"] = d.index
    parts = d["Trade"].str.split()
    d["strike"] = parts.str[0].astype(float); d["opt"] = parts.str[1]
    d["excl"] = ""
    d.loc[d.Date.isna(), "excl"] = "no date/time (incomplete OCR)"
    d.loc[d.notes.notna() & d.Date.notna(), "excl"] = "OCR note: " + d.notes.astype(str)
    d = d[d.Date.notna() | (d.excl != "")].copy()
    d["day"] = d.Date
    d["t"] = pd.to_datetime(d.Date + " " + d.Time, errors="coerce")
    d["split"] = d.day.map(lambda x: "val" if x in VALID_DAYS else "fit")
    d["hhmm"] = d.t.dt.strftime("%H:%M")
    return d.reset_index(drop=True)
