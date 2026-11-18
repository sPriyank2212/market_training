"""Minute-level feature table. Row = (index, day, minute i). All features use ONLY bars up to and including i-1
(the bar that closed just before the card's minute). y_any = >=1 card for that index at that minute."""
import numpy as np, pandas as pd
from common import *

def build():
    s = load_sigs()
    s["i"] = ((s.ts.dt.hour * 60 + s.ts.dt.minute) - 555)
    out = []
    for (idx, day), x in s.groupby(["index", "date"]):
        pass
    for day in sorted(s.date.unique()):
        for idx in ("NIFTY", "SENSEX"):
            c = load_c(idx, day).reset_index(drop=True)
            n = len(c); cl = c.close.values; op = c.open.values; hi = c.high.values; lo = c.low.values; vol = c.volume.values.astype(float)
            ret = np.r_[np.nan, np.diff(cl)]
            rng = hi - lo
            f = pd.DataFrame({"index": idx, "date": day, "i": np.arange(n)})
            S = lambda a, k: pd.Series(a).shift(1)   # previous bar value
            for k in (1, 2, 3, 5, 10, 15, 30, 60):
                f[f"r{k}"] = pd.Series(cl).shift(1) - pd.Series(cl).shift(1 + k)
            f["rng1"] = pd.Series(rng).shift(1); f["absr1"] = pd.Series(np.abs(ret)).shift(1)
            for w in (5, 10, 20):
                f[f"rv{w}"] = pd.Series(np.abs(ret)).shift(1).rolling(w).mean()
                f[f"rngx{w}"] = f.rng1 / pd.Series(rng).shift(2).rolling(w).mean()
                f[f"volx{w}"] = pd.Series(vol).shift(1) / pd.Series(vol).shift(2).rolling(w).mean()
            f["vol1"] = pd.Series(vol).shift(1)
            dh = pd.Series(hi).cummax().shift(1); dl = pd.Series(lo).cummin().shift(1)
            f["pos"] = (pd.Series(cl).shift(1) - dl) / (dh - dl).replace(0, np.nan)
            f["dist_open"] = pd.Series(cl).shift(1) - op[0]
            f["dist_hi"] = dh - pd.Series(cl).shift(1); f["dist_lo"] = pd.Series(cl).shift(1) - dl
            f["dayrng"] = dh - dl
            f["new_hi"] = (pd.Series(hi).shift(1) >= dh).astype(int); f["new_lo"] = (pd.Series(lo).shift(1) <= dl).astype(int)
            # N-bar breakout flags
            for k in (5, 10, 20):
                f[f"brk_up{k}"] = (pd.Series(cl).shift(1) > pd.Series(hi).shift(2).rolling(k).max()).astype(int)
                f[f"brk_dn{k}"] = (pd.Series(cl).shift(1) < pd.Series(lo).shift(2).rolling(k).min()).astype(int)
            f["spot"] = pd.Series(cl).shift(1)
            xs = s[(s.date == day) & (s["index"] == idx)]
            f["n_sig"] = f.i.map(xs.groupby("i").size()).fillna(0).astype(int)
            f["n_ce"] = f.i.map(xs[xs.opt == "CE"].groupby("i").size()).fillna(0).astype(int)
            f["n_pe"] = f.i.map(xs[xs.opt == "PE"].groupby("i").size()).fillna(0).astype(int)
            f["y"] = (f.n_sig > 0).astype(int)
            out.append(f)
    return pd.concat(out, ignore_index=True)

if __name__ == "__main__":
    F = build(); F.to_pickle(R / "data" / "minute_features.pkl")
    print(F.shape, F.y.mean(), F.groupby("index").y.mean().to_dict())
