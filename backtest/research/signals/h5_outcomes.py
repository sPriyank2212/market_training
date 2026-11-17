"""H5: replay every executed trade on real 1-min option highs/lows after entry; compare first-touch with recorded Status.
Entry bar = first bar j>=0 (from signal minute) in which the recorded entry price lies in [low-TOL, high+TOL]
(if none within WAIT minutes -> 'entry never reachable').  Scan bars strictly AFTER the entry bar (variant A) or
INCLUDING the entry bar (variant B).  Intra-bar ties (SL and T1 in one bar) are evaluated both ways."""
import numpy as np
from opt import *
TOL, WAIT, EOD_LAST = 0.5, 15, "15:25"

def replay(s: pd.DataFrame, E, sl, t1, t2, T, include_entry_bar: bool, tie: str):
    ent = None
    for j in range(0, WAIT + 1):
        t = T + pd.Timedelta(minutes=j)
        if t in s.index and s.loc[t, "low"] - TOL <= E <= s.loc[t, "high"] + TOL: ent = t; break
    if ent is None: return "NoEntry", None, None
    bars = s.loc[ent:] if include_entry_bar else s.loc[ent + pd.Timedelta(minutes=1):]
    bars = bars[bars.index.strftime("%H:%M") <= EOD_LAST]
    for t, b in bars.iterrows():
        hit_sl, hit1, hit2 = b.low <= sl, b.high >= t1, b.high >= t2
        if hit_sl and hit1: 
            r = "SL Hit" if tie == "sl" else ("Target Hit" if hit2 else "Target 1 Hit"); return r, t, ent
        if hit_sl: return "SL Hit", t, ent
        if hit2: return "Target Hit", t, ent
        if hit1: return "Target 1 Hit", t, ent
    return "EOD Close", None, ent

if __name__ == "__main__":
    A = pd.read_csv(OUT / "h4_table.csv", parse_dates=["T"])
    A = A[A.E.notna() & A.status.isin(["Target 1 Hit", "SL Hit", "Target Hit", "EOD Close"])].copy()
    h3 = pd.read_csv(OUT / "h3_table.csv")[["row", "code"]]; A = A.merge(h3, on="row", how="left")
    res = []
    for _, r in A.iterrows():
        s = series(r.idx, r.day, int(r.code) if pd.notna(r.code) else 1, r.opt, r.strike)
        rec = dict(row=r.row, idx=r.idx, day=r.day, split=r.split, rec=r.status, trade=f"{r.strike:.0f}{r.opt}", T=r["T"])
        for name, inc in (("A", False), ("B", True)):
            for tie in ("sl", "t1"):
                rec[f"{name}_{tie}"] = replay(s, r.E, r.sl, r.t1, r.t2, r["T"], inc, tie)[0]
        res.append(rec)
    R = pd.DataFrame(res); R.to_csv(OUT / "h5_table.csv", index=False)
    def norm_(x): return x.replace({"Target Hit": "Target 1 Hit"})        # T1 vs T2 handled separately
    pd.set_option("display.width", 200)
    print("executed rows replayed:", len(R))
    for v in ("A_sl", "A_t1", "B_sl", "B_t1"):
        ag = (norm_(R[v]) == norm_(R.rec))
        print(f"{v}: agreement all {ag.mean():.3f} | fit {ag[R.split=='fit'].mean():.3f} (n={int((R.split=='fit').sum())}) | val {ag[R.split=='val'].mean():.3f} (n={int((R.split=='val').sum())})  | NoEntry {int((R[v]=='NoEntry').sum())}")
    print("\nConfusion (variant B, SL-first ties): rows=recorded, cols=replay"); print(pd.crosstab(R.rec, R["B_sl"]).to_string())
    print("\nConfusion (variant A, SL-first ties):"); print(pd.crosstab(R.rec, R["A_sl"]).to_string())
    print("\nTie-order sensitivity: rows whose result changes if intra-bar order flips (B):", int((R.B_sl != R.B_t1).sum()), "of", len(R))
