"""Main runner: days -> signals -> gate -> entries -> exits -> P&L report.

Usage:  [BACKTEST_VERSION=v1] python backtest.py

Modelling rules (v1):
  * Candidates from BOTH indices are processed in chronological order (entry = signal-bar close).
  * One DayState is shared by NIFTY + SENSEX (day brake, SL chain/timeout and trade cap are account-level).
  * One open position per index at a time; a candidate that fires while that index's position is open is
    SKIPPED with reason OPEN. A candidate whose bar closes at/after flatten_time is SKIPPED with reason LATE.
  * Exits are settled into the state only once their exit time has passed (no look-ahead into C6/C7).
Reports two totals SEPARATELY:
  * sanity total over config sanity.days (2026: Oct 5, 6, 7, 14, 16) -> REFERENCE ONLY in own-scanner mode;
    compared to the target +/- tolerance only in engine_gate mode (the +13,452 came from the engine's own 101 signals)
  * full-range total (Oct 5-17)                            -> additional evidence, NEVER compared
A control run with the gate switched off (own-scanner, ungated) is reported for context only; it is NOT
the broker engine, so it is not comparable to the research doc's -788.
"""
from __future__ import annotations

import sys
import time as _time
from dataclasses import replace
from datetime import date, timedelta

import pandas as pd

import gate as G
import premium as P
from candles import IST, CandleStore, compute_features
from dhan_client import load_config, results_dir
from exits import simulate_exit
from ledger import make_row, write_ledger

INDICES = ["NIFTY", "SENSEX"]


def load_engine_signals(cfg: dict) -> pd.DataFrame:
    """engine_gate mode: CSV with columns date,time,index,side (side = CE/PE or +1/-1). Cached on cfg."""
    if "_engine_signals" not in cfg:
        path = cfg["run"].get("engine_signals_csv", "")
        if not path:
            raise ValueError("run.scanner = engine_gate needs run.engine_signals_csv (date,time,index,side)")
        df = pd.read_csv(path)
        missing = {"date", "time", "index", "side"} - set(df.columns)
        if missing:
            raise ValueError(f"engine signals CSV missing columns {sorted(missing)}")
        df["index"] = df["index"].astype(str).str.upper()
        df["side"] = df["side"].map(lambda x: 1 if str(x).strip().upper() in ("CE", "1", "+1", "BUY_CE", "CALL") else -1)
        df["date"] = df["date"].astype(str).str[:10]
        cfg["_engine_signals"] = df
    return cfg["_engine_signals"]


def engine_candidates(cfg: dict, sym: str, day: date, feat: pd.DataFrame):
    """Map each engine signal (clock time t) to the LAST COMPLETED 5-min bar (ts_close <= t): features and the entry premium come from that
    bar, so nothing after t is used (no look-ahead). Returns (cands, nobar) where nobar are signals before the first completed bar."""
    sigs = load_engine_signals(cfg)
    sigs = sigs[(sigs["index"] == sym) & (sigs["date"] == f"{day:%Y-%m-%d}")]
    cands, nobar = [], []
    for r in sigs.itertuples(index=False):
        t = pd.Timestamp(f"{r.date} {r.time}", tz=IST)
        done = feat.index[feat["ts_close"] <= t]
        if len(done) == 0:
            nobar.append((t, sym, int(r.side))); continue
        j = int(done[-1]); fr = feat.iloc[j]
        cands.append((fr["ts_close"], sym, j, G.Signal(index=sym, ts=t, side=int(r.side), m5=float(fr.m5), m30=float(fr.m30), rng=float(fr.rng),
                                                      trend=float(fr.trend), close=float(fr.close))))
    return cands, nobar


def run_day(cfg: dict, store: CandleStore, day: date, gated: bool = True) -> list[dict]:
    feats, cands, nobar_rows = {}, [], []
    engine = cfg["run"].get("scanner", "own") == "engine_gate"
    for sym in INDICES:
        df = store.get_day(sym, day)
        if df.empty:
            continue
        feats[sym] = compute_features(df, cfg)
        if engine:
            cs, nb = engine_candidates(cfg, sym, day, feats[sym])
            cands += cs
            nobar_rows += [make_row(date=f"{day:%Y-%m-%d}", time=t.strftime("%H:%M"), index=s_, side="CE" if sd > 0 else "PE",
                                    verdict="SKIP", skip_reason="NOBAR", mode=cfg["mode"]) for t, s_, sd in nb]
        else:
            for i, sig in G.candidate_rows(feats[sym], sym, cfg):
                cands.append((feats[sym]["ts_close"].iloc[i], sym, i, sig))
    cands.sort(key=lambda c: (c[0], c[1]))

    flat = pd.Timestamp(f"{day:%Y-%m-%d} {cfg['exits']['flatten_time']}", tz=IST)
    state, pending, rows = G.DayState(), {}, []
    for entry_ts, sym, i, sig in cands:
        for s, res in sorted(((s, r) for s, r in pending.items() if r.exit_ts <= entry_ts),
                             key=lambda kv: kv[1].exit_ts):            # settle finished trades in time order
            state.register_exit(res.pnl, res.is_sl, res.exit_ts, cfg)
            del pending[s]

        cache = cfg.setdefault("_path_cache", {})                 # the sanity / gated / ungated runs share identical premium paths
        key = (sym, day, i, sig.side)
        if key not in cache:
            cache[key] = P.get_path(feats[sym], i, sig.side, sym, cfg)
        contract, path = cache[key]
        prem = float(path["p_close"].iloc[0])
        sig = replace(sig, premium=prem)
        v = G.evaluate(sig, state, cfg)
        vetoes = (["OPEN"] if sym in pending else []) + (["LATE"] if entry_ts >= flat else [])
        gate_reason = v.skip_reason if gated else ""
        take = not vetoes and not gate_reason
        lot = cfg["risk"]["lot_size"][sym]

        row = dict(date=f"{day:%Y-%m-%d}", time=sig.ts.strftime("%H:%M"), index=sym, contract=contract.label,
                   side="CE" if sig.side > 0 else "PE", entry=round(prem, 2), lot=lot,
                   sm5=round(sig.m5 * sig.side, 2),
                   sm30=round(sig.m30 * sig.side, 2) if sig.m30 == sig.m30 else "",
                   rng=round(sig.rng, 3), mode=contract.mode, **v.checks,
                   verdict="TAKE" if take else "SKIP", skip_reason=";".join(vetoes + ([gate_reason] if gate_reason else [])))
        if take:
            state.register_entry()
            res = simulate_exit(prem, path.iloc[1:], lot, cfg)
            pending[sym] = res
            row.update(exit=round(res.exit_price, 2), exit_reason=res.exit_reason, pnl=round(res.pnl, 2))
        rows.append(row)
    return nobar_rows + rows


def run_range(cfg: dict, store: CandleStore, start: date, end: date, gated: bool = True) -> list[dict]:
    rows, d = [], start
    while d <= end:
        if d.weekday() < 5:
            rows += run_day(cfg, store, d, gated)
        d += timedelta(days=1)
    return rows


# --------------------------------------------------------------------------- reporting
def day_table(df: pd.DataFrame) -> pd.DataFrame:
    t = df[df.verdict == "TAKE"].assign(pnl=lambda x: pd.to_numeric(x.pnl))
    g = df.groupby(["date", "index"]).size().rename("cand").to_frame()
    g["taken"] = t.groupby(["date", "index"]).size()
    g["wins"] = t[t.pnl > 0].groupby(["date", "index"]).size()
    g["losses"] = t[t.pnl < 0].groupby(["date", "index"]).size()
    g["pnl"] = t.groupby(["date", "index"]).pnl.sum()
    g = g.fillna(0)
    g[["taken", "wins", "losses"]] = g[["taken", "wins", "losses"]].astype(int)
    return g.reset_index()


def total(df: pd.DataFrame, days: list[str] | None = None) -> tuple[float, int]:
    t = df[df.verdict == "TAKE"]
    if days is not None:
        t = t[t.date.isin(days)]
    return float(pd.to_numeric(t.pnl).sum()), len(t)


def _check_stats(df: pd.DataFrame) -> pd.Series:
    cols = [c for c in ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8"] if c in df]
    return pd.Series({c: int((df[c] == "FAIL").sum()) for c in cols})


def print_report(cfg: dict, gated: pd.DataFrame, raw: pd.DataFrame, runtime: float) -> None:
    sn, tgt, tol = cfg["sanity"]["days"], cfg["sanity"]["gate_target"], cfg["sanity"]["tolerance"]
    engine = cfg["run"].get("scanner", "own") == "engine_gate"
    rs = lambda v: f"{'-' if v < 0 else '+'}₹{abs(v):,.0f}"
    dt = day_table(gated)
    print(f"\n=== Strategy {cfg['version']} | scanner={cfg['run'].get('scanner', 'own')} | premium mode={cfg['mode']} | gated per-day summary ===")
    print(dt.assign(pnl=lambda x: x.pnl.map(lambda v: f"{v:,.0f}")).to_string(index=False))
    print("\nper-day totals (both indices):")
    pd_ = dt.groupby("date").agg(cand=("cand", "sum"), taken=("taken", "sum"), pnl=("pnl", "sum"))
    print(pd_.assign(pnl=lambda x: x.pnl.map(lambda v: f"{v:,.0f}")).to_string())

    nt = int((gated.verdict == "TAKE").sum()); ns = int((gated.verdict == "SKIP").sum())
    print(f"\nTAKE / SKIP (gated): {nt} / {ns}  of {len(gated)} candidates | ungated control would take {int((raw.verdict == 'TAKE').sum())}")
    st = _check_stats(gated)
    print("failures per check (gated candidates):", st.to_dict(), "| most-failed check:", st.idxmax(), f"({int(st.max())})")
    print("C8 NA rows:", int((gated.get("C8") == "NA").sum()) if "C8" in gated else 0)
    print("\nskip reasons (gated run, SKIP rows; a row can carry several):")
    print(gated[gated.verdict == "SKIP"].skip_reason.str.split(";").explode().value_counts().to_string())
    print("\nexit reasons (taken trades):", gated[gated.verdict == "TAKE"].exit_reason.value_counts().to_dict())

    s_pnl, s_n = total(gated, sn)
    f_pnl, f_n = total(gated)
    r_pnl, r_n = total(raw)
    rs_pnl, rs_n = total(raw, sn)
    print("\n" + "=" * 78)
    print(f"SANITY DAYS ({', '.join(d[5:] for d in sn)}), gate: {rs(s_pnl)} over {s_n} trades")
    if engine:
        print(f"  engine-gate mode: target {rs(tgt)} ± ₹{tol}  ->  diff {rs(s_pnl - tgt)}  ->  {'WITHIN TOLERANCE' if abs(s_pnl - tgt) <= tol else 'OUTSIDE TOLERANCE'}")
    else:
        print(f"  REFERENCE ONLY (own-scanner + synthetic premiums): the {rs(tgt)} research figure came from the engine's own 101 signals with screenshot "
              f"fills, so it is NOT comparable and nothing was tuned toward it.")
    print(f"FULL WINDOW {cfg['run']['start']}..{cfg['run']['end']} (gate): {rs(f_pnl)} over {f_n} trades")
    print(f"CONTROL own-scanner UNGATED (context only, not the broker engine): sanity days {rs(rs_pnl)} ({rs_n} trades), full window {rs(r_pnl)} ({r_n} trades)")
    print(f"gate effect vs control: sanity days {rs(s_pnl - rs_pnl)} | full window {rs(f_pnl - r_pnl)}")
    print(f"runtime {runtime:.1f}s")
    print("=" * 78)


def main() -> int:
    t0 = _time.time()
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")   # the rupee sign must not crash cp1252 consoles
        except Exception:
            pass
    cfg = load_config()
    store = CandleStore(cfg)
    if cfg.get("validation"):                      # data-validation gate: runs on every run, after fetch, before any backtest
        from validate import validate_days
        ok, _ = validate_days(store, cfg)
        if not ok:
            print("DATA VALIDATION FAILED - backtest NOT run.")
            return 2
    if cfg.get("expiries"):                        # resolve weekly expiries from the trading calendar and assert the known dates
        from expiries import attach_expiries
        attach_expiries(cfg, store)
    start, end = date.fromisoformat(cfg["run"]["start"]), date.fromisoformat(cfg["run"]["end"])

    # 1) the sanity days first (non-trading days are skipped silently)
    sanity_rows = []
    for d in cfg["sanity"]["days"]:
        sanity_rows += run_day(cfg, store, date.fromisoformat(d), True)
    sdf = write_ledger(sanity_rows, results_dir(cfg) / "ledger_sanity_days_gated.csv")
    print("\n=== Sanity days first (gated) ===")
    print(day_table(sdf).assign(pnl=lambda x: x.pnl.map(lambda v: f"{v:,.0f}")).to_string(index=False))

    # 2) the full window, gated and ungated control
    gated = write_ledger(run_range(cfg, store, start, end, True), results_dir(cfg) / "ledger_gated.csv")
    raw = write_ledger(run_range(cfg, store, start, end, False), results_dir(cfg) / "ledger_ungated_control.csv")
    day_table(gated).to_csv(results_dir(cfg) / "daily_summary_gated.csv", index=False)
    print_report(cfg, gated, raw, _time.time() - t0)
    print(f"network calls this run: {store.network_calls}")
    print(f"ledgers + summary written to {results_dir(cfg)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
