"""H1 step 1: single-feature separation of signal minutes from matched random minutes (AUC), fit days only,
with day-level bootstrap CI. AUC>0.5 => signals have HIGHER values than controls."""
from __future__ import annotations
import sys, numpy as np
from scipy.stats import rankdata
from h1_table import *

def auc(x_s, x_c):
    x = np.concatenate([x_s, x_c]); r = rankdata(x)
    n1, n0 = len(x_s), len(x_c)
    return (r[:n1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)

def auc_day_boot(df, col, B=300, seed=1):
    d = df[[col, "kind", "day"]].dropna(); days = d.day.unique()
    a = auc(d[d.kind == "signal"][col].values, d[d.kind == "control"][col].values)
    rng = np.random.default_rng(seed); bs = []
    grp = {k: v for k, v in d.groupby("day")}
    for _ in range(B):
        pick = rng.choice(days, size=len(days), replace=True)
        b = pd.concat([grp[k] for k in pick])
        s, c = b[b.kind == "signal"][col].values, b[b.kind == "control"][col].values
        if len(s) > 5 and len(c) > 5: bs.append(auc(s, c))
    return a, np.percentile(bs, 2.5), np.percentile(bs, 97.5), len(d[d.kind == "signal"])

FEATS = [c for c in ["s_ret1", "s_ret3", "s_ret5", "s_ret10", "s_retz1", "s_retz3", "s_retz5", "s_retz10",
                     "a_ret1", "a_ret3", "a_ret5", "a_ret10", "rng1", "rng3", "rng5", "rng10",
                     "volx1", "volx3", "volx5", "volx10", "s_vwap", "s_ext", "s_open", "s_pc",
                     "s_brk5", "s_brk10", "s_brk15", "s_brk30", "dh_d", "dl_d", "sig1", "tod"]]

if __name__ == "__main__":
    off = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    t = build(off); t = t[t.excl == ""]
    res = []
    for sym in ("NIFTY", "SENSEX"):
        for f in FEATS:
            sub = t[(t.idx == sym) & (t.split == "fit")]
            if f not in sub or sub[f].notna().sum() < 30: continue
            a, lo, hi, n = auc_day_boot(sub, f)
            res.append(dict(idx=sym, feat=f, auc=a, lo=lo, hi=hi, n_sig=n))
    r = pd.DataFrame(res); r["dev"] = (r.auc - .5).abs()
    r.to_csv(OUT / f"h1_auc_fit_off{off}.csv", index=False)
    pd.set_option("display.width", 200)
    for sym in ("NIFTY", "SENSEX"):
        print(f"--- {sym} (fit days, offset {off}) top 12 by |AUC-0.5|")
        print(r[r.idx == sym].sort_values("dev", ascending=False).head(12).round(3).to_string(index=False))
