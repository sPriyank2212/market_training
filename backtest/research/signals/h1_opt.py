"""H1 (option-level): does the SIGNALLED OPTION's own recent behaviour (premium momentum, premium breakout, IV change,
option volume) separate signal minutes from matched random minutes on the SAME contract? Fit days, then validation."""
import numpy as np
from opt import *
from h1_auc import auc, auc_day_boot
from h1_table import SEED, NCTRL, WIN, EXCL

def ofeat(s: pd.DataFrame) -> pd.DataFrame:
    c, h, l, v = s.close, s.high, s.low, s.volume.astype(float)
    f = pd.DataFrame(index=s.index)
    for n in (1, 3, 5, 10):
        f[f"o_ret{n}"] = (c / c.shift(n) - 1) * 100
    for n in (5, 10, 15, 30):
        f[f"o_brk{n}"] = (c > h.rolling(n).max().shift(1)).astype(float)
        f[f"o_pos{n}"] = (c - l.rolling(n).min()) / (h.rolling(n).max() - l.rolling(n).min()).replace(0, np.nan)
    f["o_ivchg5"] = s.iv - s.iv.shift(5); f["o_ivchg1"] = s.iv - s.iv.shift(1)
    f["o_volx1"] = v / v.rolling(60, min_periods=15).mean().shift(1)
    f["o_volx5"] = v.rolling(5).sum() / (v.rolling(60, min_periods=15).mean().shift(5) * 5)
    f["o_rng5"] = (h.rolling(5).max() - l.rolling(5).min()) / c * 100
    f["o_px"] = c
    return f

if __name__ == "__main__":
    rng = np.random.default_rng(SEED)
    h3 = pd.read_csv(OUT / "h3_table.csv")[["row", "code"]]
    S = signals(); S = S[S.t.notna() & (S.excl == "")].merge(h3, on="row", how="left")
    S = S[np.array([have_day(i, d) for i, d in zip(S.idx, S.day)])]
    rows = []
    for (sym, day), g in S.groupby(["idx", "day"]):
        blocked = {t + pd.Timedelta(minutes=k) for t in g.t for k in range(-EXCL, EXCL + 1)}
        for _, r in g.iterrows():
            code = int(r.code) if pd.notna(r.code) else 1
            s = series(sym, day, code, r.opt, r.strike)
            if len(s) < 60: continue
            F = ofeat(s); t0 = r.t - pd.Timedelta(minutes=1)
            if t0 not in F.index: continue
            rows.append(dict(kind="signal", idx=sym, day=day, split=r.split, **F.loc[t0].to_dict()))
            cand = [t for t in F.index if abs((t - r.t) / pd.Timedelta(minutes=1)) <= WIN and t not in blocked and 560 <= t.hour * 60 + t.minute <= 915]
            for k in rng.choice(len(cand), size=min(NCTRL, len(cand)), replace=False):
                tc = cand[k] - pd.Timedelta(minutes=1)
                if tc in F.index: rows.append(dict(kind="control", idx=sym, day=day, split=r.split, **F.loc[tc].to_dict()))
    T = pd.DataFrame(rows); T.to_csv(OUT / "h1_opt_table.csv", index=False)
    feats_ = [c for c in T.columns if c.startswith("o_") and c != "o_px"]
    res = []
    for sym in ("NIFTY", "SENSEX"):
        for sp in ("fit", "val"):
            sub = T[(T.idx == sym) & (T.split == sp)]
            for f in feats_:
                d = sub[[f, "kind"]].dropna()
                if (d.kind == "signal").sum() < 15: continue
                a, lo, hi, n = auc_day_boot(sub, f, B=200)
                res.append(dict(idx=sym, split=sp, feat=f, auc=a, lo=lo, hi=hi, n_sig=n))
    R = pd.DataFrame(res); R.to_csv(OUT / "h1_opt_auc.csv", index=False)
    pd.set_option("display.width", 200)
    for sym in ("NIFTY", "SENSEX"):
        p = R[R.idx == sym].pivot(index="feat", columns="split", values="auc"); p["dev"] = (p.fit - .5).abs()
        print(f"--- {sym}: option-feature AUC (signal vs same-contract random minutes)"); print(p.sort_values("dev", ascending=False).head(10).round(3).to_string())
