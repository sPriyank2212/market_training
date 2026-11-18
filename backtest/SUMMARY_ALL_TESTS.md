> **CORRECTION (2026-11-18): the v1 results in this file used 2025 candles, but the engine signals and the +₹13,452 target are from October 2026.** The v1 sections (§2, §1 'Test 1' row and the sensitivity/headline numbers) are INVALID; a corrected re-run is `versions/v3/`. The v2 research (2022–2026 data) is not affected by the date mix-up.

# Backtester — consolidated summary of ALL tests (v1 + v2)

Project: read-only Dhan-API backtester for the NIFTY/SENSEX "eight-check gate" (`market_training/backtest/`).
Detail files live in `versions/v1/results/` and `versions/v2/results/`.

## 1. At a glance
| | Version | What was tested | Verdict |
|---|---|---|---|
| **Test 1** | v1 (frozen) | The spec'd strategy: own-scanner bursts + 8-check gate + SL/T1/T2 bracket, 10 trading days (Oct 5–17 2025) | Built and working; **research target NOT reproduced** (+₹53 vs +₹13,452) |
| **Test 2** | v2 (research) | Does a burst have a real edge? 4.9 years of data, train/test split, option costs | **No robustly profitable strategy.** One small, decaying, execution-sensitive NIFTY candidate |

Software tests: **68 passed, 0 failed** (exits 12, features 5, gate 27, ledger 3, premium 9, security 12).

## 2. Test 1 — v1 milestones
| Milestone | Result |
|---|---|
| **M0 Scaffold** | Complete. `/orders` guard + read-only allow-list run before any network call; token masked; exact 401 message; 12 security tests pass. Python is 3.14 (spec said 3.12). |
| **M1 Dhan connection** | NIFTY 2025-10-06 = 75 bars (09:15–15:25), securityId 13; SENSEX = 51. Weekend/holiday handled. Yahoo fallback not needed. Found: datetime dates required; `fromDate` is exclusive at the boundary (start at 09:00); timestamps are true UTC epoch. |
| **M2 Cache + features** | 10 trading days × 2 indices, 75 bars each, no gaps. Re-run = 0 network calls. No look-ahead (tested). Warm-up: `m30` NaN before 09:45, `trend` before 10:15. |
| **M3 Eight-check gate** | 27 gate tests pass incl. all rulings (C5 12:00 in / 13:00 out; C7 −7000 SKIPs, −6999 passes; C1 tautology noted). 6 deliberate off-by-one bugs all caught. Preview: 201 candidates → 32 TAKE; 43 (21%) fell in the warm-up window. |
| **M4 Premium + exits** | Black-Scholes (theta emerges), SL-first tie-break tested. ATM call delta 0.531 (6.5% rate), ≈0.5 at forward strike. Finding: C8 band acts as a days-to-expiry filter (NIFTY passes only Wed–Fri). Real option API works (`expiryCode 1`; `0` rejected); real IV ≈ 8.7% vs 13% assumed. |
| **M5 Ledger + report** | Ledger columns match spec exactly. Full run 3.9 s from cache. 11 trades hand-verified (P&L arithmetic ±₹0.47). |

### v1 headline numbers (1 lot, synth premium, no slippage/brokerage)
| Measure | Result |
|---|---|
| Sanity: gate over Oct 6, 7, 14, 16 | **+₹53, 2 trades** — target +₹13,452 ±₹250 → **OUTSIDE** |
| Full range Oct 5–17, gated (not compared) | −₹1,919, 11 trades |
| Control, gate off — sanity days / full range | +₹2,197 (49 trades) / +₹4,730 (131 trades) |
| Engine raw −₹788 | Not reproducible (needs the broker engine's signals) |

Sensitivity grid (diagnostic only, nothing tuned): C8 off, lot 75, IV 9%, ITM strikes, T1 fraction, bar-close stamp → best sanity result +₹294. No assumption comes within ~₹13,000 of the target.
Likely causes: broker-engine signals ≠ my scanner; research contracts/premiums differ from nearest-weekly ATM; unclear P&L basis; tiny sample.

## 3. Test 2 — v2 research (Jan 2022 → Nov 2026, ~1,190 sessions per index)
Protocol fixed in advance: train 2022-01→2024-06, test 2024-07→2026-11; selection on train only; non-overlapping signals; day-clustered t-stats.

| Finding | Detail |
|---|---|
| Index-level edge | Continuation after big bursts lasts ~15 min (train t 3.5–5; test keeps the sign, NIFTY `cont|z3|T` t = 2.6) but shrinks (~0.38σ → 0.15σ). Fades do not survive. |
| v1 exit was mismatched | The edge is 15 minutes; v1's bracket holds for hours. |
| After option costs | Only ~20% of configs net-positive. SENSEX ≈ 0 net. |
| **NIFTY candidate** | Burst ≥ 3σ5, 60-min trend agrees, not 12:00–13:00, buy ATM option, exit after 15 min, 15% stop. |

NIFTY candidate numbers:
| | Train | Test |
|---|---|---|
| Trades | 262 | 290 |
| Net per trade (% of premium) | +3.1% | **+1.4%** (gross +2.8%) |
| Net t-stat | 3.0 | **1.45** |

Robustness: positive in 10/10 half-years but decaying (+8.4% in 2022H1 → +0.25% in 2026H1); break-even ≈ 2.1× assumed costs; bootstrap 90% CI [−0.2%, +3.1%], P(≤0) ≈ 7%; **entry one bar late → +0.6% (t 0.7), two bars late → −1.0%**; ≈ ₹146/trade at 1 lot, ≈ ₹80.7k over 4.9 years, max drawdown ≈ −₹18.2k.

## 4. Overall conclusions
1. The tool works end to end and is tested; the original research number does **not** reproduce under the stated rules.
2. The only evidence-backed edge is small, short-lived and sensitive to fills and costs. **Not ready for real money.**
3. Caveats: option prices are modelled (no bid/ask data); many configs were examined; lot sizes for Oct 2025 unverified (NIFTY 75 vs 65 would change ₹ by ~15%).

## 5. Next steps
1. Paper-trade the NIFTY rule ≥ 3 months, logging real fill times and option quotes.
2. Re-test with real option premiums (`/charts/rollingoption`, multi-strike fetch — not built yet).
3. If both hold, consider sizing; automation is deliberately out of scope for this read-only tool.

## 6. File map
- Strategy versions: `versions/v1/` (frozen, see `FROZEN.md`), `versions/v2/`
- v1 results: `M0-M2_summary.md`, `M3_summary.md`, `M4_summary.md`, `M5_summary.md`, `ledger_gated.csv`, `ledger_ungated_control.csv`, `daily_summary_gated.csv`, `M5_sensitivity_DIAGNOSTIC_ONLY.csv`, `M4_c8_premium_check.csv`, `M3_gate_preview.csv`, `M2_data_quality.csv`
- v2 results: `V2_summary.md`, `edge_study_all_configs.csv`, `option_study_all_configs.csv`
- Research code: `research/edge_study.py`, `research/option_study.py`
