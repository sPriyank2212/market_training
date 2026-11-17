"""H1 (futures / VIX): does the index future's momentum, volume, OI change, basis, or India VIX separate signal minutes
from matched random minutes? Same controls as h1_table. Fit-day AUC with day bootstrap, then the same features on val."""
import numpy as np
from h1_auc import *

def xs(name, day):
    p = CACHE / f"x_{name}_{day}.csv"
    if not p.exists(): return pd.DataFrame()
    d = pd.read_csv(p)
    if d.empty: return d
    d["ts"] = pd.to_datetime(d["ts"]); return d.set_index("ts")

def xfeat(sym, day):
    fut, vix, sp = xs(f"{sym}FUT", day), xs("VIX", day), spot(sym, day)
    f = pd.DataFrame(index=sp.index)
    c = fut.close.reindex(sp.index).ffill()
    for n in (1, 3, 5, 10): f[f"fut_ret{n}"] = (c / c.shift(n) - 1) * 1e4
    v = fut.volume.reindex(sp.index).fillna(0)
    f["fut_volx1"] = v / v.rolling(60, min_periods=15).mean().shift(1)
    f["fut_volx5"] = v.rolling(5).sum() / (v.rolling(60, min_periods=15).mean().shift(5) * 5)
    oi = fut.open_interest.reindex(sp.index).ffill()
    f["fut_doi5"] = (oi / oi.shift(5) - 1) * 1e4; f["fut_doi15"] = (oi / oi.shift(15) - 1) * 1e4
    basis = (c - sp.close) ; f["basis"] = basis; f["basis_chg5"] = basis - basis.shift(5)
    vx = vix.close.reindex(sp.index).ffill()
    f["vix"] = vx; f["vix_chg5"] = vx - vx.shift(5); f["vix_chg15"] = vx - vx.shift(15)
    return f

if __name__ == "__main__":
    t = build(0); t = t[t.excl == ""].copy()
    rows = []
    for (sym, day), g in t.groupby(["idx", "day"]):
        F = xfeat(sym, day); ts = g["T"] - pd.Timedelta(minutes=1)
        X = F.reindex(ts.values); X.index = g.index; rows.append(X)
    X = pd.concat(rows); t = t.join(X)
    d = t.dirn
    for c in ("fut_ret1", "fut_ret3", "fut_ret5", "fut_ret10", "fut_doi5", "fut_doi15", "basis_chg5", "vix_chg5", "vix_chg15"):
        t["s_" + c] = d * t[c]
    fs = ["s_fut_ret1", "s_fut_ret3", "s_fut_ret5", "s_fut_ret10", "fut_volx1", "fut_volx5", "fut_doi5", "fut_doi15", "s_fut_doi5",
          "s_fut_doi15", "basis", "s_basis_chg5", "vix", "vix_chg5", "s_vix_chg5", "vix_chg15"]
    res = []
    for sym in ("NIFTY", "SENSEX"):
        for sp in ("fit", "val"):
            sub = t[(t.idx == sym) & (t.split == sp)]
            for f in fs:
                if sub[f].notna().sum() < 30: continue
                a, lo, hi, n = auc_day_boot(sub, f, B=200); res.append(dict(idx=sym, split=sp, feat=f, auc=a, lo=lo, hi=hi, n_sig=n))
    R = pd.DataFrame(res); R.to_csv(OUT / "h1_extra_auc.csv", index=False)
    for sym in ("NIFTY", "SENSEX"):
        p = R[R.idx == sym].pivot(index="feat", columns="split", values="auc"); p["dev"] = (p["fit"] - .5).abs()
        print(f"--- {sym}: futures/VIX features AUC"); print(p.sort_values("dev", ascending=False).round(3).to_string())
