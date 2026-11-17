"""Interactive explorer: one self-contained HTML (plotly.js from cdnjs; needs internet to load the library only).
Pick a day + index -> spot chart with every signal; click a signal (or a row) -> that trade's option candles with
Entry/SL/T1/T2, signal time, entry bar and replayed exit. Re-run any time: python build_interactive.py"""
import json
from pathlib import Path
import numpy as np
from opt import *
from h5_outcomes import replay
from plot_days import day_index


def iso(ts):
    return ts.strftime("%Y-%m-%dT%H:%M:00")


def r2(x):
    return [None if pd.isna(v) else round(float(v), 2) for v in x]


def num(v):
    return None if pd.isna(v) else float(v)


def build():
    S = signals()
    S = S[S.t.notna() & (S.excl == "")]
    data = {}
    for day in sorted(S.day.unique()):
        for sym in ("NIFTY", "SENSEX"):
            if len(S[(S.idx == sym) & (S.day == day)]) == 0:
                continue
            sp = spot(sym, day)
            if sp.empty:
                continue
            vw = ((sp.high + sp.low + sp.close) / 3 * sp.volume).cumsum() / sp.volume.cumsum()
            d = {"spot": {"t": [iso(t) for t in sp.index], "o": r2(sp.open), "h": r2(sp.high), "l": r2(sp.low),
                          "c": r2(sp.close), "vwap": r2(vw)}, "trades": []}
            have = have_day(sym, day)
            g = day_index(sym, day, S) if have else S[(S.idx == sym) & (S.day == day)].sort_values("t").assign(code=1)
            for i, (_, r) in enumerate(g.iterrows()):
                tr = dict(id=i, t=iso(r.t), hhmm=r.hhmm, opt=r.opt, strike=float(r.strike),
                          status=r.status if isinstance(r.status, str) else "",
                          entry=num(r.entry), exit=num(r.exit), t1=num(r.t1), t2=num(r.t2), sl=num(r.sl), pnl=num(r.pnl),
                          expiry=r.expiry, lot=None if pd.isna(r.lot) else int(r.lot),
                          spot_at=round(float(sp.loc[r.t, "close"]), 2) if r.t in sp.index else None, ser=None, rep=None,
                          ent_t=None, exit_t=None)
                if have:
                    s = series(sym, day, int(r.code), r.opt, r.strike)
                    if len(s):
                        res, tt, ent = (None, None, None)
                        if pd.notna(r.entry) and pd.notna(r.sl):
                            res, tt, ent = replay(s, r.entry, r.sl, r.t1, r.t2, r.t, False, "sl")
                        w = s.loc[r.t - pd.Timedelta(minutes=20):]
                        tr["ser"] = {"t": [iso(t) for t in w.index], "o": r2(w.open), "h": r2(w.high), "l": r2(w.low),
                                     "c": r2(w.close), "v": [int(x) for x in w.volume.fillna(0)],
                                     "oi": [int(x) for x in w.oi.fillna(0)], "iv": r2(w.iv)}
                        tr["rep"] = res
                        tr["ent_t"] = iso(ent) if ent is not None else None
                        tr["exit_t"] = iso(tt) if tt is not None else None
                d["trades"].append(tr)
            data.setdefault(day, {})[sym] = d
    return data


if __name__ == "__main__":
    html = (Path(__file__).with_name("explorer_template.html")).read_text(encoding="utf-8")
    data = build()
    js = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    out = OUT / "charts" / "interactive.html"
    out.parent.mkdir(exist_ok=True)
    lib = (Path(__file__).with_name("vendor") / "plotly.min.js").read_text(encoding="utf-8").replace("</script", "<\/script")
    html = html.replace('<script src="https://cdnjs.cloudflare.com/ajax/libs/plotly.js/2.35.2/plotly.min.js"></script>', "<script>" + lib + "</script>")
    out.write_text(html.replace("/*DATA*/null", js), encoding="utf-8")
    n = sum(len(v["trades"]) for d in data.values() for v in d.values())
    print(f"wrote {out}  ({out.stat().st_size/1e6:.1f} MB, {len(data)} days, {n} signals)")
