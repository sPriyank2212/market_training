"""H1 final: best SIMPLE rule evaluated as a real detector over ALL minutes of each day.
Rule family (<=2 params, chosen on fit days only): fire on a rising edge of  dirn*ret_n >= theta  (n in {1,3,5}),
dirn = sign(ret_n).  Match = a firing within +-TOLM minutes of a signal in the same direction (CE for up, PE for down).
Reported: recall, precision, firings/day, and a random-firing baseline with the same number of firings per day."""
import numpy as np
from features import *
from load import signals
TOLM = 1; EXCLUDE_BEFORE = 9 * 60 + 20

def fire(F, n, th):
    r = F[f"ret{n}"]; up = r >= th; dn = r <= -th
    fu = up & ~up.shift(1, fill_value=False); fd = dn & ~dn.shift(1, fill_value=False)
    f = pd.Series(0, index=F.index); f[fu] = 1; f[fd] = -1
    f[(F.tod < EXCLUDE_BEFORE) | (F.tod > 15 * 60 + 15)] = 0
    return f

def evaluate(sym, days, n, th, sig, rng=None):
    tp_sig = tot_sig = tp_fire = tot_fire = 0; base_tp = 0
    F_all = feats(sym)
    for d in days:
        F = F_all[d]; f = fire(F, n, th); g = sig[(sig.idx == sym) & (sig.day == d)]
        # a signal at label T is "seen" by a firing whose decision bar is T-1 => firing at bar ts means label ts+1min
        lab = f[f != 0]; fire_labels = [(t + pd.Timedelta(minutes=1), v) for t, v in lab.items()]
        sig_l = [(r.t, 1 if r.opt == "CE" else -1) for _, r in g.iterrows()]
        def near(t, v, L): return any(abs((t - u) / pd.Timedelta(minutes=1)) <= TOLM and v == w for u, w in L)
        tot_sig += len(sig_l); tp_sig += sum(near(t, v, fire_labels) for t, v in sig_l)
        tot_fire += len(fire_labels); tp_fire += sum(near(t, v, sig_l) for t, v in fire_labels)
        if rng is not None and len(fire_labels):                      # baseline: same count of random labels/day
            cands = [t + pd.Timedelta(minutes=1) for t in F.index[(F.tod >= EXCLUDE_BEFORE) & (F.tod <= 15 * 60 + 15)]]
            for _ in range(20):
                pick = rng.choice(len(cands), size=len(fire_labels), replace=False)
                base_tp += sum(near(cands[i], rng.choice([1, -1]), sig_l) for i in pick) / 20
    return dict(recall=tp_sig / max(tot_sig, 1), precision=tp_fire / max(tot_fire, 1), fires=tot_fire, sigs=tot_sig,
                base_precision=base_tp / max(tot_fire, 1), n_days=len(days))

if __name__ == "__main__":
    S = signals(); S = S[S.t.notna() & (S.excl == "")]
    fitd = sorted(S[S.split == "fit"].day.unique()); vald = sorted(S[S.split == "val"].day.unique())
    rng = np.random.default_rng(7)
    out = []
    for sym in ("NIFTY", "SENSEX"):
        best = None
        for n in (1, 3, 5):
            for th in (3, 5, 7, 10, 15, 20, 30):
                e = evaluate(sym, [d for d in fitd if d in feats(sym)], n, th, S)
                f1 = 2 * e["recall"] * e["precision"] / max(e["recall"] + e["precision"], 1e-9)
                out.append(dict(idx=sym, n=n, th=th, split="fit", f1=f1, **e))
                if best is None or f1 > best[0]: best = (f1, n, th)
        _, n, th = best
        ev = evaluate(sym, vald, n, th, S, rng); ef = evaluate(sym, fitd, n, th, S, rng)
        print(f"\n{sym}: chosen on fit: ret{n} >= {th} bps (rising edge, direction=sign)")
        for nm, e in (("fit", ef), ("val", ev)):
            print(f"  {nm}: recall {e['recall']:.2f}  precision {e['precision']:.2f} (random-fire baseline {e['base_precision']:.2f})  "
                  f"firings/day {e['fires']/e['n_days']:.0f} vs signals/day {e['sigs']/e['n_days']:.1f}")
        out.append(dict(idx=sym, n=n, th=th, split="val", **ev))
    pd.DataFrame(out).to_csv(OUT / "h1_rule_grid.csv", index=False)
