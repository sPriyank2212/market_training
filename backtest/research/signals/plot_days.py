"""Per-day charts: (1) index price with every signal marked, (2) one small chart per trade showing the option premium from just
before the signal to the exit, with Entry / SL / T1 / T2 levels, signal time, entry bar and the exit.
Usage: python plot_days.py [YYYY-MM-DD ...]   -> out/charts/{day}_{INDEX}.png  and out/charts/index.html"""
import sys, math, base64, numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt, matplotlib.dates as mdates
from opt import *
from h5_outcomes import replay

CH = OUT / "charts"; CH.mkdir(exist_ok=True)
COL = {"Target 1 Hit": "#1a9850", "Target Hit": "#006837", "SL Hit": "#d73027", "Not Triggered": "#999999",
       "EOD Close": "#4575b4", "Active": "#4575b4", "Yet to Activate": "#999999"}
TOL = 0.5

def pick_code(r, grp_codes):
    best = None
    for code in (1, 2):
        s = series(r.idx, r.day, code, r.opt, r.strike)
        if s.empty: continue
        if pd.notna(r.entry):
            ok = sum(1 for j in range(-1, 6) if (r.t + pd.Timedelta(minutes=j)) in s.index and
                     s.loc[r.t + pd.Timedelta(minutes=j), "low"] - TOL <= r.entry <= s.loc[r.t + pd.Timedelta(minutes=j), "high"] + TOL)
            if best is None or ok > best[0]: best = (ok, code)
    if best: return best[1]
    return grp_codes.get((r.idx, r.day, r.expiry), 1)

def day_index(sym, day, S):
    g = S[(S.idx == sym) & (S.day == day)].sort_values("t").copy()
    ex = g[g.entry.notna()].copy()
    codes = {}
    for _, r in ex.iterrows():
        c = pick_code(r, {}); codes.setdefault((r.idx, r.day, r.expiry), []).append(c)
    gc = {k: max(set(v), key=v.count) for k, v in codes.items()}
    g["code"] = [pick_code(r, gc) for _, r in g.iterrows()]
    return g

def fmt(ax):
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M")); ax.grid(alpha=.25)

def one(sym, day, S):
    sp = spot(sym, day); g = day_index(sym, day, S)
    if sp.empty or g.empty: return None
    n = len(g); cols = 4; rows = math.ceil(n / cols)
    fig = plt.figure(figsize=(22, 4.2 + 2.6 * rows), dpi=70)
    gs = fig.add_gridspec(rows + 1, cols, height_ratios=[1.9] + [1] * rows, hspace=.75, wspace=.22)
    ax = fig.add_subplot(gs[0, :])
    ax.plot(sp.index, sp.close, color="#333", lw=1)
    ax.fill_between(sp.index, sp.low, sp.high, color="#bbb", alpha=.35, lw=0)
    vw = ((sp.high + sp.low + sp.close) / 3 * sp.volume).cumsum() / sp.volume.cumsum()
    ax.plot(sp.index, vw, color="#e08214", lw=.9, ls="--", label="VWAP")
    for _, r in g.iterrows():
        if r.t in sp.index:
            ax.scatter(r.t, sp.loc[r.t, "close"], marker="^" if r.opt == "CE" else "v", s=70, c=COL.get(r.status, "#777"),
                       edgecolors="k", linewidths=.6, zorder=5)
    ax.set_title(f"{sym}  {day}   spot 1-min  (▲ = CE signal, ▼ = PE signal;  green = target hit, red = SL hit, grey = not triggered, blue = EOD/active)   "
                 f"open {sp.open.iloc[0]:.0f}  close {sp.close.iloc[-1]:.0f}  range {sp.low.min():.0f}–{sp.high.max():.0f}", fontsize=13, loc="left")
    ax.legend(loc="upper right"); fmt(ax)
    for i, (_, r) in enumerate(g.reset_index(drop=True).iterrows()):
        a = fig.add_subplot(gs[1 + i // cols, i % cols])
        s = series(sym, day, int(r.code), r.opt, r.strike)
        title = f"{r.hhmm}  {r.Trade}  [{r.status}]" + (f"  ₹{r.pnl:+,.0f}" if pd.notna(r.pnl) else "")
        if s.empty:
            a.set_title(title, fontsize=9, color=COL.get(r.status, "k")); a.text(.5, .5, "no option data\n(strike outside ATM±10)", ha="center", va="center", transform=a.transAxes, fontsize=8); a.axis("off"); continue
        res, tt, ent = (None, None, None)
        if pd.notna(r.entry) and pd.notna(r.sl): res, tt, ent = replay(s, r.entry, r.sl, r.t1, r.t2, r.t, False, "sl")
        endt = tt if tt is not None else (r.t + pd.Timedelta(minutes=45) if res in (None, "NoEntry") else pd.Timestamp(f"{day} 15:25"))
        lo_t, hi_t = r.t - pd.Timedelta(minutes=12), min(endt + pd.Timedelta(minutes=12), pd.Timestamp(f"{day} 15:29"))
        w = s.loc[lo_t:hi_t]
        if w.empty:
            a.set_title(title, fontsize=9, color=COL.get(r.status, 'k')); a.text(.5, .5, 'no option candles in window', ha='center', va='center', transform=a.transAxes, fontsize=8); a.axis('off'); continue
        a.fill_between(w.index, w.low, w.high, color="#9ecae1", alpha=.6, lw=0); a.plot(w.index, w.close, color="#08519c", lw=1)
        for val, c, ls, nm in ((r.entry, "k", "-", "entry"), (r.sl, "#d73027", "--", "SL"), (r.t1, "#1a9850", "--", "T1"), (r.t2, "#006837", ":", "T2")):
            if pd.notna(val): a.axhline(val, color=c, ls=ls, lw=1); a.text(w.index[0], val, f" {nm} {val:g}", fontsize=7, color=c, va="bottom")
        a.axvline(r.t, color="#e08214", lw=1.2); 
        if ent is not None: a.scatter(ent, r.entry, marker="o", s=34, c="k", zorder=5)
        if tt is not None: a.scatter(tt, r.sl if res == "SL Hit" else r.t1, marker="X", s=60, c=COL.get(res, "k"), zorder=6, edgecolors="k")
        a.set_title(title, fontsize=9, color=COL.get(r.status, "k")); fmt(a); a.tick_params(labelsize=7)
        a.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=5))
        if res and res != "NoEntry" and r.status in COL and res.replace("Target Hit", "Target 1 Hit") != r.status.replace("Target Hit", "Target 1 Hit"):
            a.text(.99, .02, f"replay says: {res}", transform=a.transAxes, ha="right", fontsize=7, color="purple")
    p = CH / f"{day}_{sym}.png"; fig.savefig(p, bbox_inches="tight"); plt.close(fig); return p

if __name__ == "__main__":
    S = signals(); S = S[S.t.notna() & (S.excl == "")]
    days = sys.argv[1:] or sorted(S.day.unique())
    made = []
    for day in days:
        for sym in ("NIFTY", "SENSEX"):
            if len(S[(S.idx == sym) & (S.day == day)]) == 0: continue
            if not have_day(sym, day): print("skip (no option data yet)", sym, day); continue
            p = one(sym, day, S); 
            if p: made.append((day, sym, p)); print("wrote", p.name, flush=True)
    allp = sorted(CH.glob("*.png"))
    html = ["<html><meta charset='utf-8'><title>Signals by day</title><body style='font-family:sans-serif;background:#fafafa'><h2>Signals by day — spot, signal, option premium and exit</h2>"]
    for p in allp:
        html.append(f"<h3>{p.stem.replace('_', '  ')}</h3><img style='max-width:100%' src='data:image/png;base64,{base64.b64encode(p.read_bytes()).decode()}'>")
    (CH / "index.html").write_text("\n".join(html) + "</body></html>", encoding="utf-8"); print("index.html:", len(allp), "charts")
