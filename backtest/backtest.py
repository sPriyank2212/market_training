"""Main runner: days -> signals -> gate -> entries -> exits -> P&L report.

Usage:  [BACKTEST_VERSION=v1] python backtest.py

Modelling rules (v1):
  * Candidates from BOTH indices are processed in chronological order (entry = signal-bar close).
  * One DayState is shared by NIFTY + SENSEX (day brake, SL chain/timeout and trade cap are account-level).
  * One open position per index at a time; a candidate that fires while that index's position is open is
    SKIPPED with reason OPEN. A candidate whose bar closes at/after flatten_time is SKIPPED with reason LATE.
  * Exits are settled into the state only once their exit time has passed (no look-ahead into C6/C7).
Reports two totals SEPARATELY:
  * sanity total over config sanity.days (Oct 6, 7, 14, 16) -> compared to target +/- tolerance
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


def run_day(cfg: dict, store: CandleStore, day: date, gated: bool = True) -> list[dict]:
    feats, cands = {}, []
    for sym in INDICES:
        df = store.get_day(sym, day)
        if df.empty:
            continue
        feats[sym] = compute_features(df, cfg)
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

        contract, path = P.get_path(feats[sym], i, sig.side, sym, cfg)
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
    return rows


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


def print_report(cfg: dict, gated: pd.DataFrame, raw: pd.DataFrame, runtime: float) -> None:
    sn, tgt, tol = cfg["sanity"]["days"], cfg["sanity"]["gate_target"], cfg["sanity"]["tolerance"]
    rs = lambda v: f"{'-' if v < 0 else '+'}₹{abs(v):,.0f}"
    dt = day_table(gated)
    print(f"\n=== Strategy {cfg['version']} | mode={cfg['mode']} | gated per-day summary ===")
    out = dt.assign(pnl=lambda x: x.pnl.map(lambda v: f"{v:,.0f}"))
    print(out.to_string(index=False))
    print("\nskip reasons (gated run, SKIP rows; a row can carry several):")
    sk = gated[gated.verdict == "SKIP"].skip_reason.str.split(";").explode().value_counts()
    print(sk.to_string())
    print("\nexit reasons (taken trades):", gated[gated.verdict == "TAKE"].exit_reason.value_counts().to_dict())

    s_pnl, s_n = total(gated, sn)
    f_pnl, f_n = total(gated)
    print("\n" + "=" * 78)
    print(f"SANITY (gate, {', '.join(d[5:] for d in sn)} only): {rs(s_pnl)}  over {s_n} trades")
    print(f"  target {rs(tgt)} ± ₹{tol}  ->  diff {rs(s_pnl - tgt)}  ->  {'WITHIN TOLERANCE' if abs(s_pnl - tgt) <= tol else 'OUTSIDE TOLERANCE'}")
    print(f"FULL RANGE {cfg['run']['start']}..{cfg['run']['end']} (gate, additional evidence, not compared): "
          f"{rs(f_pnl)} over {f_n} trades")
    r_pnl, r_n = total(raw)
    rs_pnl, rs_n = total(raw, sn)
    print(f"CONTROL own-scanner UNGATED (not the broker engine; context only): sanity days {rs(rs_pnl)} ({rs_n} trades), "
          f"full range {rs(r_pnl)} ({r_n} trades)")
    print(f"gate effect on sanity days vs control: {rs(s_pnl - rs_pnl)}")
    print(f"runtime {runtime:.1f}s")
    print("=" * 78)


def main() -> int:
    t0 = _time.time()
    cfg = load_config()
    store = CandleStore(cfg)
    start, end = date.fromisoformat(cfg["run"]["start"]), date.fromisoformat(cfg["run"]["end"])
    gated = write_ledger(run_range(cfg, store, start, end, True), results_dir(cfg) / "ledger_gated.csv")
    raw = write_ledger(run_range(cfg, store, start, end, False), results_dir(cfg) / "ledger_ungated_control.csv")
    day_table(gated).to_csv(results_dir(cfg) / "daily_summary_gated.csv", index=False)
    print_report(cfg, gated, raw, _time.time() - t0)
    print(f"network calls this run: {store.network_calls}")
    print(f"ledgers + summary written to {results_dir(cfg)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
