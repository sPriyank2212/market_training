"""H1 step 2: AUC of key features vs clock offset (-3..+3 min), fit days only."""
from h1_auc import *
rows = []
for off in range(-3, 4):
    t = build(off); t = t[(t.excl == "") & (t.split == "fit")]
    for sym in ("NIFTY", "SENSEX"):
        for f in ("s_ret1", "s_ret3", "s_ret5", "s_ret10", "rng3", "a_ret1", "s_vwap", "s_ext", "volx1"):
            sub = t[t.idx == sym]
            d = sub[[f, "kind"]].dropna()
            rows.append(dict(idx=sym, off=off, feat=f, auc=auc(d[d.kind == "signal"][f].values, d[d.kind == "control"][f].values)))
r = pd.DataFrame(rows).pivot_table(index=["idx", "feat"], columns="off", values="auc").round(3)
r.to_csv(OUT / "h1_offset_profile_fit.csv"); print(r.to_string())
