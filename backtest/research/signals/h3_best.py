"""H3b: which candle price best matches the recorded entry premium? (offset j in -2..+2 minutes, price definition)."""
import numpy as np
from opt import *
H = pd.read_csv(OUT / "h3_table.csv"); S = signals().set_index("row")
rows = []
for _, r in H[H.code.notna()].iterrows():
    s = series(r.idx, r.day, int(r.code), S.loc[r.row, "opt"], S.loc[r.row, "strike"]); T = pd.Timestamp(r["T"])
    for j in range(-2, 3):
        t = T + pd.Timedelta(minutes=j)
        if t not in s.index: continue
        b = s.loc[t]
        for nm, p in (("open", b.open), ("close", b.close), ("mid(H,L)", (b.high + b.low) / 2), ("high", b.high), ("low", b.low), ("ohlc4", (b.open + b.high + b.low + b.close) / 4)):
            rows.append(dict(split=r.split, j=j, price=nm, err=r.entry - p, rel=(r.entry / p - 1) * 100))
R = pd.DataFrame(rows)
g = R.groupby(["price", "j"]).agg(n=("err", "size"), med_err=("err", "median"), mae=("err", lambda x: x.abs().mean()),
                                 within1=("err", lambda x: (x.abs() <= 1).mean()), within1pct=("rel", lambda x: (x.abs() <= 1).mean()),
                                 within2pct=("rel", lambda x: (x.abs() <= 2).mean())).round(3)
print(g.sort_values("mae").head(8).to_string())
best = g.sort_values("mae").index[0]; print("best on all:", best)
for sp in ("fit", "val"):
    x = R[(R.split == sp) & (R.price == best[0]) & (R.j == best[1])]
    print(sp, "n", len(x), "within Rs1", round((x.err.abs() <= 1).mean(), 3), "within 1%", round((x.rel.abs() <= 1).mean(), 3), "within 2%", round((x.rel.abs() <= 2).mean(), 3),
          "median |err|", round(x.err.abs().median(), 2), "p90 |err|", round(x.err.abs().quantile(.9), 2))
