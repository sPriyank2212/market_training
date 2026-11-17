"""H2b: is the strike chosen by a PREMIUM target (or delta target) instead of a fixed distance from ATM?
At the last closed bar before the signal, list every strike of that side reachable (ATM+-10) with its premium; predict
the strike whose premium is closest to P (P fixed per index, chosen on FIT days), compare with the actual strike.
Baselines: best constant ITM offset (k steps from ATM)."""
import numpy as np
from opt import *
from scipy.stats import norm

def snapshot(S):
    h3 = pd.read_csv(OUT / "h3_table.csv")[["row", "code"]]
    S = S.merge(h3, on="row", how="left"); rows = []
    for _, r in S.iterrows():
        code = int(r.code) if pd.notna(r.code) else 1
        b = book(r.idx, r.day, code, r.opt)
        if b.empty: continue
        t0 = r.t - pd.Timedelta(minutes=1); cur = b[b.ts == t0]
        if cur.empty or r.strike not in set(cur.strike): continue
        spot_ = float(cur.spot.iloc[0]); st = STEP[r.idx]
        exp = pd.Timestamp(r.expiry + " 15:30"); T = max((exp - t0) / pd.Timedelta(minutes=1), 5) / 525600
        cc = cur.copy(); iv = (cc.iv / 100).clip(lower=.03)
        d1 = (np.log(spot_ / cc.strike) + (.065 + .5 * iv**2) * T) / (iv * np.sqrt(T))
        cc["delta"] = norm.cdf(d1) if r.opt == "CE" else -norm.cdf(-d1)
        act = cc[cc.strike == r.strike].iloc[0]
        rows.append(dict(row=r.row, idx=r.idx, day=r.day, split=r.split, opt=r.opt, strike=r.strike, atm=round(spot_ / st) * st, st=st,
                         px=float(act.close), delta=abs(float(act.delta)), cands=cc[["strike", "close", "delta"]].values))
    return rows

def acc(rows, f, tol=0):
    ok = 0
    for r in rows:
        c = r["cands"]; pred = c[f(c), 0]
        ok += abs(pred - r["strike"]) <= tol * r["st"]
    return ok / max(len(rows), 1)

if __name__ == "__main__":
    S = signals(); S = S[S.t.notna() & (S.excl == "")]
    R = snapshot(S); print("signals with a full strike ladder at decision bar:", len(R))
    for sym, grid in (("NIFTY", range(60, 321, 10)), ("SENSEX", range(100, 701, 20))):
        fit = [r for r in R if r["idx"] == sym and r["split"] == "fit"]; val = [r for r in R if r["idx"] == sym and r["split"] == "val"]
        print(f"\n=== {sym}: fit n={len(fit)}  val n={len(val)}")
        bestP = max(grid, key=lambda P: acc(fit, lambda c: np.argmin(np.abs(c[:, 1] - P))))
        print(f"premium-target rule  P={bestP}: exact strike fit {acc(fit, lambda c: np.argmin(np.abs(c[:, 1]-bestP))):.3f} val {acc(val, lambda c: np.argmin(np.abs(c[:, 1]-bestP))):.3f} | within 1 step fit {acc(fit, lambda c: np.argmin(np.abs(c[:, 1]-bestP)), 1):.3f} val {acc(val, lambda c: np.argmin(np.abs(c[:, 1]-bestP)), 1):.3f}")
        dg = [x / 100 for x in range(30, 96, 5)]
        bd = max(dg, key=lambda D: acc(fit, lambda c: np.argmin(np.abs(np.abs(c[:, 2]) - D))))
        print(f"delta-target rule    D={bd}: exact fit {acc(fit, lambda c: np.argmin(np.abs(np.abs(c[:, 2])-bd))):.3f} val {acc(val, lambda c: np.argmin(np.abs(np.abs(c[:, 2])-bd))):.3f} | within 1 step fit {acc(fit, lambda c: np.argmin(np.abs(np.abs(c[:, 2])-bd)), 1):.3f} val {acc(val, lambda c: np.argmin(np.abs(np.abs(c[:, 2])-bd)), 1):.3f}")
        def kacc(rows, k): return np.mean([(((r["atm"] - r["strike"]) / r["st"] if r["opt"] == "CE" else (r["strike"] - r["atm"]) / r["st"]) == k) for r in rows])
        bk = max(range(-3, 6), key=lambda k: kacc(fit, k))
        print(f"constant ITM offset  k={bk}: exact fit {kacc(fit, bk):.3f} val {kacc(val, bk):.3f}   (baseline)")
        pxs = np.array([r["px"] for r in fit + val]); print(f"premium of chosen strike: p10/p50/p90 = {np.percentile(pxs,10):.0f}/{np.percentile(pxs,50):.0f}/{np.percentile(pxs,90):.0f}")
