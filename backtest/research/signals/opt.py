"""Assemble fixed-strike option series from rolling ATM+k files. Strike S at bar ts is available iff some k in
[-10,10] has strike(ts)==S. Series are per (sym, day, expiry-code, side)."""
from __future__ import annotations
from functools import lru_cache
import numpy as np
from load import *

@lru_cache(maxsize=None)
def book(sym: str, day: str, code: int, side: str) -> pd.DataFrame:
    parts = []
    for k in range(-10, 11):
        d = option(sym, day, code, side, k)
        if len(d): parts.append(d.assign(k=k))
    if not parts: return pd.DataFrame()
    b = pd.concat(parts).reset_index().rename(columns={"index": "ts"})
    b = b[(b.ts.dt.hour * 60 + b.ts.dt.minute >= 555) & (b.ts.dt.hour * 60 + b.ts.dt.minute < 930)]
    return b

def series(sym: str, day: str, code: int, side: str, strike: float) -> pd.DataFrame:
    b = book(sym, day, code, side)
    if b.empty: return b
    s = b[b.strike == strike].drop_duplicates("ts").set_index("ts").sort_index()
    return s

def have_day(sym, day, code=1):
    return bool(len(option(sym, day, code, "CE", 0)))
