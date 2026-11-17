"""Per-minute spot features using only CLOSED bars (bar `ts` covers [ts, ts+1min)). Feature row at ts is
available at ts+1min. Used by H1 for signals and random controls."""
from __future__ import annotations
import numpy as np
from load import *

def day_features(sym: str, day: str, prev_close: float | None) -> pd.DataFrame:
    s = spot(sym, day)
    if s.empty: return s
    c, h, l, v = s.close, s.high, s.low, s.volume.astype(float)
    f = pd.DataFrame(index=s.index)
    f["close"] = c
    r1 = c.pct_change() * 1e4                         # bps
    sig = r1.rolling(30, min_periods=10).std().shift(1)  # trailing 1-min vol (bps), excludes current bar
    f["sig1"] = sig
    for n in (1, 3, 5, 10):
        f[f"ret{n}"] = (c / c.shift(n) - 1) * 1e4
        f[f"retz{n}"] = f[f"ret{n}"] / (sig * np.sqrt(n))
        f[f"rng{n}"] = (h.rolling(n).max() - l.rolling(n).min()) / c * 1e4
        vs = v.rolling(n).sum()
        base = v.rolling(60, min_periods=15).mean().shift(n) * n
        f[f"volx{n}"] = vs / base
    tp = (h + l + c) / 3
    vw = (tp * v).cumsum() / v.cumsum().replace(0, np.nan)
    f["vwap_d"] = (c / vw - 1) * 1e4
    dh, dl = h.cummax(), l.cummin()
    f["dh_d"] = (c / dh - 1) * 1e4           # <=0 ; 0 means at day high
    f["dl_d"] = (c / dl - 1) * 1e4           # >=0 ; 0 means at day low
    f["open_d"] = (c / s.open.iloc[0] - 1) * 1e4
    if prev_close: f["pc_d"] = (c / prev_close - 1) * 1e4
    for n in (5, 10, 15, 30):
        f[f"brkup{n}"] = (c > h.rolling(n).max().shift(1)).astype(float)
        f[f"brkdn{n}"] = (c < l.rolling(n).min().shift(1)).astype(float)
    for n in (15, 30, 60):
        f[f"ret{n}"] = (c / c.shift(n) - 1) * 1e4
    e9, e21 = c.ewm(span=9, adjust=False).mean(), c.ewm(span=21, adjust=False).mean()
    f["ema_d"] = (e9 / e21 - 1) * 1e4
    dlt = c.diff(); up, dn = dlt.clip(lower=0), (-dlt).clip(lower=0)
    rs = up.ewm(alpha=1 / 14, adjust=False).mean() / dn.ewm(alpha=1 / 14, adjust=False).mean().replace(0, np.nan)
    f["rsi14"] = 100 - 100 / (1 + rs)
    # forming 5-minute candle (clock-aligned: 09:15, 09:20, ...) and previous completed 5-min candle
    grp = (s.index.hour * 60 + s.index.minute - 555) // 5
    o5 = s.open.groupby(grp).transform("first"); h5 = h.groupby(grp).cummax(); l5 = l.groupby(grp).cummin()
    f["f5_ret"] = (c / o5 - 1) * 1e4                       # move since the forming 5m candle opened
    ph = h.groupby(grp).max().shift(1); pl = l.groupby(grp).min().shift(1)
    f["f5_brkup"] = (c > grp.map(ph).values).astype(float); f["f5_brkdn"] = (c < grp.map(pl).values).astype(float)
    f["f5_pos"] = (s.index.minute - 15) % 5                # minute within the 5-min candle
    f["nbar"] = np.arange(len(f))
    f["tod"] = f.index.hour * 60 + f.index.minute
    return f

_cache: dict = {}
def feats(sym: str) -> dict[str, pd.DataFrame]:
    if sym in _cache: return _cache[sym]
    days = sorted(p.name.split("_")[2][:10] for p in CACHE.glob(f"spot_{sym}_*.csv"))
    out, prev = {}, None
    for d in days:
        s = spot(sym, d)
        if s.empty: continue
        out[d] = day_features(sym, d, prev); prev = float(s.close.iloc[-1])
    _cache[sym] = out; return out
