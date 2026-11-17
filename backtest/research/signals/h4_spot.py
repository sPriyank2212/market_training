"""H4b: are SL/T1/T2 SPOT-derived? Convert each premium distance to spot points via a fixed delta (0.5 and per-trade BS delta),
then test (a) are the implied spot distances 'round' (multiples of 10/20 pts) (b) do they match recent swing low/high or ATR multiples."""
import numpy as np
from opt import *
A = pd.read_csv(OUT / "h4_table.csv", parse_dates=["T"]); X = A[A.E.notna()].copy()
X["DS"], X["D1"], X["D2"] = X.E - X.sl, X.t1 - X.E, X.t2 - X.E
pd.set_option("display.width", 200)
for sym in ("NIFTY", "SENSEX"):
    g = X[X.idx == sym]
    print(f"\n=== {sym} (n={len(g)})  implied SPOT distance = premium distance / delta")
    for dl_name, dl in (("fixed 0.5", 0.5), ("BS delta", g.delta)):
        for c in ("DS", "D1", "D2"):
            pts = g[c] / dl; step = 10 if sym == "NIFTY" else 20
            near = (np.abs(pts - (pts / step).round() * step) <= step * 0.15).mean()
            print(f"  {dl_name:9s} {c}: median {pts.median():6.1f} pts, CV {pts.std()/pts.mean():.2f}, within 15% of a {step}-pt grid: {near:.2f}")
# swing / ATR matches
rows = []
for _, r in X.iterrows():
    sp = spot(r.idx, r.day); t0 = r["T"] - pd.Timedelta(minutes=1)
    if t0 not in sp.index: continue
    w = sp.loc[:t0]; s0 = float(w.close.iloc[-1]); sgn = 1 if r.opt == "CE" else -1
    d = dict(idx=r.idx, split=r.split, DSpts=r.DS / 0.5, D1pts=r.D1 / 0.5, D2pts=r.D2 / 0.5)
    for n in (5, 10, 15, 30, 60):
        ww = w.tail(n)
        d[f"swing{n}"] = (s0 - ww.low.min()) if sgn > 0 else (ww.high.max() - s0)      # distance to adverse swing (SL candidate)
        d[f"fav{n}"] = (ww.high.max() - s0) if sgn > 0 else (s0 - ww.low.min())          # distance to favourable swing
        d[f"atr{n}"] = (ww.high - ww.low).mean()
    d["dayrng"] = float(w.high.max() - w.low.min()); rows.append(d)
R = pd.DataFrame(rows)
print("\nCorrelation of implied SPOT SL distance (premium dist / 0.5) with spot features (fit | val):")
for sym in ("NIFTY", "SENSEX"):
    for sp_ in ("fit", "val"):
        g = R[(R.idx == sym) & (R.split == sp_)]
        cs = {c: round(g[["DSpts", c]].corr().iloc[0, 1], 2) for c in ("swing5", "swing10", "swing15", "swing30", "atr5", "atr15", "atr30", "dayrng")}
        print(f" {sym} {sp_} n={len(g)}:", cs)
print("\nSame for T1 / T2 distances vs favourable swing / ATR:")
for sym in ("NIFTY", "SENSEX"):
    g = R[R.idx == sym]
    print(f" {sym} T1:", {c: round(g[["D1pts", c]].corr().iloc[0, 1], 2) for c in ("fav15", "fav30", "fav60", "atr15", "atr30", "dayrng")},
          " T2:", {c: round(g[["D2pts", c]].corr().iloc[0, 1], 2) for c in ("fav15", "fav30", "fav60", "atr15", "atr30", "dayrng")})
