"""H1 step 3: how well can ANY linear combination of the spot features separate signal minutes from matched
random minutes? Leave-one-day-out CV on fit days (L2 logistic regression, weights balance classes), then ONE frozen
evaluation on the validation days. CEILING for linear 'spot features only' rules, not a rule itself."""
import warnings; warnings.filterwarnings("ignore")
import numpy as np
from scipy.optimize import minimize
from h1_auc import *

X = ["s_ret1", "s_ret3", "s_ret5", "s_ret10", "s_ret15", "s_ret30", "a_ret1", "a_ret3", "a_ret5", "rng1", "rng3", "rng5", "rng10",
     "volx1", "volx3", "volx5", "s_vwap", "s_ext", "s_open", "s_ema", "s_rsi", "s_f5", "s_f5brk", "s_brk5", "s_brk10", "s_brk15", "sig1", "tod"]

class Logit:
    def __init__(self, C=0.3): self.C = C
    def fit(self, X, y, w):
        self.mu = np.nanmedian(X, 0); X = np.where(np.isnan(X), self.mu, X)
        self.m, self.s = X.mean(0), X.std(0) + 1e-9; Z = (X - self.m) / self.s
        Z = np.c_[np.ones(len(Z)), Z]
        def f(b):
            z = Z @ b; p = 1 / (1 + np.exp(-z))
            ll = -(w * (y * np.log(p + 1e-12) + (1 - y) * np.log(1 - p + 1e-12))).sum() + 0.5 / self.C * (b[1:] ** 2).sum()
            g = Z.T @ (w * (p - y)); g[1:] += b[1:] / self.C
            return ll, g
        self.b = minimize(f, np.zeros(Z.shape[1]), jac=True, method="L-BFGS-B").x; return self
    def predict(self, X):
        X = np.where(np.isnan(X), self.mu, X); return np.c_[np.ones(len(X)), (X - self.m) / self.s] @ self.b

t = build(0); t = t[t.excl == ""].copy(); t["y"] = (t.kind == "signal").astype(int)
t["w"] = np.where(t.y == 1, 1.0, 1.0 / 20)
out = []
for sym in ("NIFTY", "SENSEX"):
    d = t[t.idx == sym]; fit, val = d[d.split == "fit"], d[d.split == "val"]
    oof = pd.Series(np.nan, index=fit.index)
    for day in fit.day.unique():
        tr, te = fit[fit.day != day], fit[fit.day == day]
        oof[te.index] = Logit().fit(tr[X].values, tr.y.values, tr.w.values).predict(te[X].values)
    a_cv = auc(oof[fit.y == 1].values, oof[fit.y == 0].values)
    m = Logit().fit(fit[X].values, fit.y.values, fit.w.values); p = m.predict(val[X].values)
    a_val = auc(p[val.y.values == 1], p[val.y.values == 0])
    out.append(dict(idx=sym, model="logit(L2)", auc_fit_LODO=round(a_cv, 3), auc_val=round(a_val, 3),
                    n_sig_fit=int(fit.y.sum()), n_sig_val=int(val.y.sum())))
r = pd.DataFrame(out); print(r.to_string(index=False)); r.to_csv(OUT / "h1_ceiling.csv", index=False)
