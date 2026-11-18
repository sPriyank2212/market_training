# v3 — M5 ledger + report (2026 data, own-scanner, synthetic premiums)

Run: `python backtest.py` (validation gate -> expiry resolution/assertion -> sanity days first -> full window -> ungated control). **Offline from cache: 0 network calls, 3.9 s runtime (8.3 s wall incl. start-up) < 10 s.** 96 tests pass (incl. engine_gate mode and the mutation self-check).

## Results (1 lot, synthetic premium IV 13 %, no slippage/brokerage)
| | P&L | trades |
|---|---|---|
| Sanity days 05, 06, 07, 14, 16 Oct — gate (reference only) | **-₹4,422** | 5 |
| Full window 05–17 Oct — gate | **-₹7,451** | 8 |
| Control, own-scanner UNGATED — sanity days / full window | +₹2,027 / **+₹7,101** | 91 / 196 |
| Gate effect vs control | -₹6,448 / -₹14,552 | |

The +₹13,452 research figure is **not comparable** (it came from the engine's own 101 signals with screenshot fills; this run is own-scanner with modelled premiums) and nothing was tuned toward it. Gated exits: SL 6, T1 1, EOD 1.

Per-day gate P&L: 05-Oct -1,139 | 06-Oct -1,043 | 07/08/09-Oct 0 | 12-Oct -1,113 | 13-Oct -1,916 | 14-Oct +400 | 15-Oct 0 | 16-Oct -2,639. 289 candidates: 8 TAKE / 281 SKIP; most-failed check C4 (176); C2 145, C8 140, C3 139, C5 33, C6 2, C7 0, C1 0 (tautology); also LATE 18, OPEN 4.

## Investigation of the "surprising" result (diagnostic only — no thresholds touched)
- Of the 196 control trades, the **7 that pass the gate lost -₹6,364** (7 stop-outs), while the **189 the gate would skip made +₹13,464** (win rate overall 61 %, 56 T2 exits). The sample behind the gated figure is tiny (8 trades).
- Entry premium matters: NIFTY control trades in the 120–215 band earned +₹8,606 (47 trades); SENSEX 120–215 band lost -₹2,189.
- Vetoed trades by a single failing check: C2 +₹483 (4), C4 +₹581 (5), C3 -₹594 (6), C8 only -₹2,215 (3) — individually small, so the damage comes from the combination removing most winning entries, not from one rule.
- Consistent with the v2 research (continuation after bursts has a short-lived edge): vetoing "exhausted" (C2) and range-extreme (C4) entries removes continuation entries — hypothesis, not proof. The gate was designed for the engine's signals, not for this scanner's, which is why the engine-gate A/B matters.
- Data/fill assumptions checked first: SENSEX synthetic premium is 16–19 % cheaper than real at the flat 13 % IV and NIFTY 4–11 % richer (M4), which shifts who passes the C8 band; expiry-day/1-DTE candidates (112 of 289) fail C8 regardless of the one-step ITM rule.

## Deliverables
`ledger_gated.csv`, `ledger_ungated_control.csv`, `ledger_sanity_days_gated.csv`, `daily_summary_gated.csv` — 24 spec columns (date, time, index, contract, side, entry, lot, exit, exit_reason, pnl, sm5, sm30, rng, C1..C8, verdict, skip_reason, mode); plain CSV, opens in Excel. `engine_gate` mode (CSV date,time,index,side) is built and tested (uses the last completed 5-min bar at the signal time, no look-ahead; C1 is then meaningful) but **no 5–16 Oct signal list has been supplied**, so it has not been run on that window.
