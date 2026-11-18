# v3 — Backtest summary (2026 re-run, M0–M5) — short version

**Why a re-run:** v1 fetched 2025 candles by mistake; the engine signals and the +₹13,452 target are Oct 2026. v1's conclusions are invalid. v3 = same strategy logic, correct year, plus a data-validation gate.
**Setup:** own-scanner, synthetic Black-Scholes premium (IV 13 %), 1 lot, no slippage/brokerage, 5–16 Oct 2026 (10 trading days, NIFTY + SENSEX).

## Milestones
| M | What | Result |
|---|---|---|
| 0 | Scaffold | v3 config (2026 dates, anchors, known expiries); v1 marked invalid |
| 1 | Dhan connection | NIFTY/SENSEX 6-Oct: 75 bars, 09:15–15:25, year 2026; weekend/holiday skipped |
| 1.5 | Validation gate | NIFTY 10/10 OK. SENSEX: 4 anchor FAILs came only from the 15:20/15:25 bars (Dhan's 15:20 bar is flat). **You chose:** strict check on bars ≤ 15:15 (max bar diff 0.114 %, tolerance 0.15 %), late bars warn. **20 rows: 11 OK, 9 WARN, 0 FAIL** |
| 2 | Cache + features | 20 series × 75 bars, no gaps, no look-ahead. 289 burst candidates, **76 (26 %)** in warm-up (NaN → fail) |
| 3 | Eight-check gate | 27 gate tests + 6/6 mutants killed. Preview 289 → 18 TAKE (before premium) |
| 4 | Premium + exits | Expiries from trading calendar (NIFTY Mon 19 Oct holiday shift) – 6/6 known dates asserted. Dynamic ITM step: 149 stepped; 149 in band, 116 still below, 24 above. Model vs real: NIFTY +4–11 % rich, SENSEX −16–19 % cheap |
| 5 | Ledger + report | See results below. 96 tests pass; 3.9 s offline, 0 network calls |

## Results
| | P&L | Trades |
|---|---|---|
| Sanity days (5, 6, 7, 14, 16 Oct), gate — *reference only* | **−₹4,422** | 5 |
| Full window, gate | **−₹7,451** | 8 (6 SL, 1 T1, 1 EOD) |
| Control (gate off), sanity days / full window | +₹2,027 / **+₹7,101** | 91 / 196 |
| Gate effect vs control (full window) | −₹14,552 | |

The +₹13,452 target is **not comparable** (engine's own 101 signals, real fills) and nothing was tuned toward it.

**Candidates 289 → TAKE 8 / SKIP 281.** Failures per check: C4 176 · C2 145 · C8 140 · C3 139 · C5 33 · C6 2 · C7 0 · C1 0 (tautology). Also LATE 18, OPEN 4.

## Why the gate looks bad (diagnostic, nothing tuned)
- Control trades that **pass** the gate: 7 trades, **−₹6,364** (all stop-outs). Trades the gate **skips**: 189 trades, **+₹13,464**. Control win rate 61 %, 56 T2 exits.
- NIFTY 120–215 premium band: +₹8,606 (47 trades). SENSEX same band: −₹2,189.
- Likely cause: the gate vetoes continuation entries (C2/C4), which fits the v2 finding (short-lived continuation edge). Hypothesis only; sample behind the gated figure is **8 trades**.

## Caveats
- Synthetic premiums, flat IV; real-premium mode not built. Engine-gate mode built and tested, **not run** (no 5–16 Oct signal list).
- Sanity result is from 5 gated trades — not statistically meaningful.

## Other studies (same project)
- **v2 research (2022–2026):** NIFTY 15-min continuation edge after bursts: test +1.4 %/trade, t 1.45, decaying, dies with a 1-bar delay. SENSEX ≈ 0. No robust profitable strategy.
- **Signals reverse-engineering (19 Oct–13 Nov):** trigger not found (best rule recall 0.35 / precision 0.12); strike ≈ premium target (₹160 NIFTY / ₹300 SENSEX); SL ≈ fixed ₹ templates; replay reproduces recorded status 88 %.

Details: `M0-M1_summary.md`, `M1_5_summary.md`, `M2_summary.md`, `M3_summary.md`, `M4_summary.md`, `M5_summary.md`; ledgers `ledger_*.csv`.
