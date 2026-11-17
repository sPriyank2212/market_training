"""H3: where does the recorded entry premium sit in the real 1-min option candles around the signal minute?
For each executed signal: pick expiry code (1 nearest / 2 next) by best in-range match, then for offsets j=-3..+10
test whether entry lies inside [low,high] of bar T+j (tolerance TOL), and compute errors vs open/close/mid of bar T+j."""
import sys, numpy as np
from opt import *
TOL = 0.5     # Rs; feed differences between Dhan and the app's feed
JS = list(range(-3, 11))

def rows_for(S):
    out = []
    for _, r in S.iterrows():
        rec = dict(row=r.row, idx=r.idx, day=r.day, split=r.split, trade=r.Trade, T=r.t, entry=r.entry, expiry=r.expiry,
                   status=r.status, code=np.nan)
        best = None
        for code in (1, 2):
            s = series(r.idx, r.day, code, r.opt, r.strike)
            if s.empty: continue
            hit = 0
            for j in range(-1, 6):
                t = r.t + pd.Timedelta(minutes=j)
                if t in s.index and s.loc[t, "low"] - TOL <= r.entry <= s.loc[t, "high"] + TOL: hit += 1
            cand = (hit, -abs((s.reindex([r.t + pd.Timedelta(minutes=j) for j in range(0, 3)]).close.mean() - r.entry)), code)
            if best is None or cand[:2] > best[:2]: best = cand
        if best is None: out.append(rec); continue
        code = best[2]; rec["code"] = code
        s = series(r.idx, r.day, code, r.opt, r.strike)
        rec["inrange_any_-1_5"] = best[0] > 0
        for j in JS:
            t = r.t + pd.Timedelta(minutes=j)
            if t in s.index:
                b = s.loc[t]
                rec[f"in{j:+d}"] = bool(b.low - TOL <= r.entry <= b.high + TOL)
                if j in (-1, 0, 1, 2):
                    rec[f"eO{j:+d}"] = r.entry - b.open; rec[f"eC{j:+d}"] = r.entry - b.close
                    rec[f"eM{j:+d}"] = r.entry - (b.high + b.low) / 2
            else:
                rec[f"in{j:+d}"] = np.nan
        # first minute j>=-3 at which entry is reachable
        first = next((j for j in JS if rec.get(f"in{j:+d}") is True), np.nan); rec["first_in"] = first
        out.append(rec)
    return pd.DataFrame(out)

if __name__ == "__main__":
    S = signals(); S = S[S.t.notna() & (S.excl == "") & S.entry.notna()]
    S = S[np.array([have_day(i, d) for i, d in zip(S.idx, S.day)])]
    days = sorted(S.day.unique())
    R = rows_for(S); R.to_csv(OUT / "h3_table.csv", index=False)
    pd.set_option("display.width", 220)
    print("rows", len(R), " with option data", int(R.code.notna().sum()), " days", len(days))
    ok = R[R.code.notna()]
    print("\nexpiry code chosen:", ok.code.value_counts().to_dict())
    print("entry reachable in some bar j=-1..5:", round(ok["inrange_any_-1_5"].mean(), 3))
    print("\nShare with entry inside [low,high] of bar T+j (all/fit/val):")
    tab = pd.DataFrame({sp: ok[ok.split == sp][[f"in{j:+d}" for j in JS]].astype(float).mean() for sp in ("fit", "val")})
    tab["all"] = ok[[f"in{j:+d}" for j in JS]].astype(float).mean(); print(tab.round(3).to_string())
    print("\nfirst bar offset where entry becomes reachable:"); print(ok.first_in.value_counts(dropna=False).sort_index().to_string())
    for j in (0, 1):
        for k, nm in (("eO", "open"), ("eC", "close"), ("eM", "mid")):
            e = ok[f"{k}{j:+d}"].dropna()
            print(f"entry - {nm}(T{j:+d}): median {e.median():+.2f}  MAD {np.median(np.abs(e - e.median())):.2f}  within Rs1: {(e.abs() <= 1).mean():.3f}  within Rs0.5: {(e.abs() <= .5).mean():.3f}")
