"""Collate per-signal verdicts: which signals the best simple rule (H1), the strike rule (H2) and the replay (H5) can / cannot explain."""
import numpy as np
from features import *
from h1_rule import fire, TOLM
from h2_premium import snapshot
H1RULE = {"NIFTY": (3, 5), "SENSEX": (5, 7)}      # chosen on FIT days in h1_rule.py (ret_n >= th bps)
S = signals(); allrows = S.copy()
S = S[S.t.notna() & (S.excl == "")].copy()
fires = {}
for sym, (n, th) in H1RULE.items():
    for d, F in feats(sym).items():
        f = fire(F, n, th); fires[(sym, d)] = [(t + pd.Timedelta(minutes=1), v) for t, v in f[f != 0].items()]
S["h1_caught"] = [any(abs((t - u) / pd.Timedelta(minutes=1)) <= TOLM and v == (1 if o == "CE" else -1) for u, v in fires.get((i, d), []))
                  for i, d, t, o in zip(S.idx, S.day, S.t, S.opt)]
P = {"NIFTY": 160, "SENSEX": 300}
snap = {r["row"]: r for r in snapshot(S)}
def h2(r):
    s = snap.get(r.row)
    if s is None: return np.nan
    c = s["cands"]; pred = c[np.argmin(np.abs(c[:, 1] - P[r.idx])), 0]; return abs(pred - r.strike) <= s["st"]
S["h2_within1step"] = S.apply(h2, axis=1)
h5 = pd.read_csv(OUT / "h5_table.csv")[["row", "rec", "A_sl"]]; h5["h5_agree"] = h5.rec.replace({"Target Hit": "Target 1 Hit"}) == h5.A_sl.replace({"Target Hit": "Target 1 Hit"})
S = S.merge(h5[["row", "A_sl", "h5_agree"]].rename(columns={"A_sl": "replay"}), on="row", how="left")
out = pd.concat([S[["row", "idx", "day", "split", "hhmm", "Trade", "status", "entry", "pnl", "h1_caught", "h2_within1step", "replay", "h5_agree"]],
                 allrows[allrows.excl != ""].assign(hhmm=lambda d: d.hhmm)[["row", "idx", "day", "split", "hhmm", "Trade", "status", "excl"]]], ignore_index=True)
out.to_csv(OUT / "per_signal_verdicts.csv", index=False)
print("signals evaluated:", len(S), "| excluded:", int((allrows.excl != "").sum()))
for sp in ("fit", "val"):
    g = S[S.split == sp]; print(sp, "H1 caught:", round(g.h1_caught.mean(), 3), " H2 within 1 step:", round(g.h2_within1step.dropna().astype(float).mean(), 3), " H5 agree:", round(g.h5_agree.dropna().astype(float).mean(), 3))
print("\nStatus disagreements (recorded vs replay):"); d = S[S.h5_agree == False][["day", "hhmm", "Trade", "status", "replay"]]; print(d.groupby(["status", "replay"]).size().to_string())
print("\nexcluded rows:"); print(allrows[allrows.excl != ""][["idx", "Trade", "day", "hhmm", "excl"]].to_string())
