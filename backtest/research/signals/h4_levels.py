"""H4: how are SL / T1 / T2 derived? Compare candidate models by dispersion (coefficient of variation) of the implied
quantity and by OLS R^2 with <=3 parameters, fit days -> validation days.
Models for D1=T1-E, D2=T2-E, DS=E-SL (Rs):  (a) % of entry   (b) fixed Rs   (c) spot points x delta   (d) option's own recent range."""
import numpy as np
from opt import *
from scipy.stats import norm
R_ = 0.065

def delta_bs(S, K, tmin, iv, is_call):
    T = max(tmin, 5) / (365 * 24 * 60); sg = max(iv, 0.03)
    d1 = (np.log(S / K) + (R_ + 0.5 * sg**2) * T) / (sg * np.sqrt(T))
    return norm.cdf(d1) if is_call else norm.cdf(d1) - 1

def build_table():
    S = signals(); S = S[S.t.notna() & (S.excl == "") & S.t1.notna() & S.sl.notna()].copy()
    S = S[np.array([have_day(i, d) for i, d in zip(S.idx, S.day)])]
    h3 = pd.read_csv(OUT / "h3_table.csv")[["row", "code"]]
    S = S.merge(h3, on="row", how="left")
    out = []
    for _, r in S.iterrows():
        code = int(r.code) if pd.notna(r.code) else 1
        s = series(r.idx, r.day, code, r.opt, r.strike); sp = spot(r.idx, r.day)
        if s.empty: continue
        t0 = r.t - pd.Timedelta(minutes=1)       # last closed bar
        if t0 not in s.index or t0 not in sp.index: continue
        px = float(s.loc[t0, "close"]); iv = float(s.loc[t0, "iv"]) / 100.0
        spt = float(sp.loc[t0, "close"])
        exp = pd.Timestamp(r.expiry + " 15:30"); tmin = (exp - t0) / pd.Timedelta(minutes=1)
        dl = abs(delta_bs(spt, r.strike, tmin, iv, r.opt == "CE"))
        w = lambda n: sp.loc[:t0].tail(n)
        so = lambda n: s.loc[:t0].tail(n)
        rec = dict(row=r.row, idx=r.idx, day=r.day, split=r.split, opt=r.opt, strike=r.strike, T=r.t, status=r.status,
                   E=r.entry, t1=r.t1, t2=r.t2, sl=r.sl, px=px, iv=iv, spot=spt, delta=dl, dte=(exp.normalize() - pd.Timestamp(r.day)).days,
                   spATR5=(w(5).high - w(5).low).mean(), spATR15=(w(15).high - w(15).low).mean(), spATR30=(w(30).high - w(30).low).mean(),
                   opATR5=(so(5).high - so(5).low).mean(), opATR15=(so(15).high - so(15).low).mean(), opATR30=(so(30).high - so(30).low).mean(),
                   opR15=so(15).high.max() - so(15).low.min())
        out.append(rec)
    return pd.DataFrame(out)

def cv(x): x = x.dropna(); return x.std() / abs(x.mean())

if __name__ == "__main__":
    A = build_table(); A.to_csv(OUT / "h4_table.csv", index=False)
    X = A[A.E.notna()].copy()                     # executed trades have a recorded entry
    X["D1"], X["D2"], X["DS"] = X.t1 - X.E, X.t2 - X.E, X.E - X.sl
    # Use the market premium at signal bar for non-triggered rows too (px) -> same quantities
    A["D1p"], A["D2p"], A["DSp"] = A.t1 - A.px, A.t2 - A.px, A.px - A.sl
    pd.set_option("display.width", 200)
    print("rows", len(A), "executed", len(X))
    for sym in ("NIFTY", "SENSEX"):
        g = X[X.idx == sym]
        print(f"\n=== {sym} (n={len(g)}): coefficient of variation of each implied quantity (lower = more constant)")
        rows = []
        for nm, d in (("D1", g.D1), ("D2", g.D2), ("DS", g.DS)):
            rows.append(dict(level=nm, Rs=cv(d), pct_of_E=cv(d / g.E), per_delta_pts=cv(d / g.delta), pct_of_spot=cv(d / g.spot),
                             per_spATR15=cv(d / (g.spATR15 * g.delta)), per_opATR15=cv(d / g.opATR15), per_opR15=cv(d / g.opR15),
                             per_iv_sqrtE=cv(d / (g.E * g.iv))))
        print(pd.DataFrame(rows).round(2).to_string(index=False))
    # Rs 5 rounding: is each level exactly on the 5-grid?
    print("\nlevels on 5-grid:", {c: round(float((A[c] % 5 == 0).mean()), 3) for c in ("t1", "t2", "sl")})
    print("px vs E at the signal bar (executed): median diff", round(float((X.E - X.px).median()), 2), "MAD", round(float((X.E - X.px).sub((X.E - X.px).median()).abs().median()), 2))
