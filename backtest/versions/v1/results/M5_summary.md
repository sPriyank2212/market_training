# M5 — Ledger + report  ✅ built  |  Sanity target: ❌ NOT reproduced

Run: `python backtest.py` (v1, mode synth, from cache: **3.9 s for gated + ungated runs, 0 network calls**; budget <10 s).
Outputs in this folder: `ledger_gated.csv`, `ledger_ungated_control.csv`, `daily_summary_gated.csv`, `M5_sensitivity_DIAGNOSTIC_ONLY.csv`.

## Headline numbers (1 lot, synth premium, no slippage/brokerage)
| Measure | Result |
|---|---|
| **Sanity: gate over Oct 6, 7, 14, 16** | **+₹53 over 2 trades** — target +₹13,452 ±₹250 → **OUTSIDE** (gap −₹13,399) |
| Full range Oct 5–17, gated (not compared) | −₹1,919 over 11 trades (4 SL, 3 EOD, 2 T2, 2 T1) |
| Control: own-scanner, gate OFF — sanity days | +₹2,197 over 49 trades |
| Control: gate OFF — full range | +₹4,730 over 131 trades |
| Engine raw −₹788 | **Not reproducible**: needs the broker engine's own signals; the own-scanner control is a different signal set and is not compared |

Gate effect: 201 candidates → 11 trades. SKIP reasons (a row can have several): C8 112, C3 89, C2 85, C4 81, C5 26, C6 9, LATE 8, OPEN 7. C1 and C7 never fired (expected / no −₹7,000 day).

## Is it a bug? Checked.
- All 11 trades hand-checked: P&L = (avg exit − entry) × lot to ±₹0.47 rounding; SL exits at exactly 0.85× entry; T2 average exit = 1.165× entry (50% at T1, 50% at T2) ✓.
- Shared day state works across indices (e.g. Oct 13 NIFTY signal vetoed by C6 after two SENSEX stops).
- Ledger columns match the spec exactly (tested). Settlement of exits into C6/C7 state happens only after the exit time (no look-ahead).
- Tests: 68 passed.

## Why the target is out of reach (diagnostic sensitivity, NOT tuning; v1 unchanged)
`M5_sensitivity_DIAGNOSTIC_ONLY.csv` — sanity-day gate P&L under alternative assumptions:
| Scenario | Sanity P&L | Trades |
|---|---|---|
| v1 baseline | +53 | 2 |
| C8 band off | −511 | 5 |
| Lot NIFTY 75 | +53 | 2 |
| IV 9% (≈ real) | 0 | 0 |
| 1-step ITM | +84 | 2 |
| T1 sells 33% / 100% | +294 / −550 | 2 |
| signal stamp = bar close | +53 | 2 |
| Gate OFF (control) | +2,197 | 49 |
| Best combination tried | +294 | — |

No fill, lot, IV, contract-selection or stamp assumption comes within ₹13,000 of the target. A single perfect full-T2 trade is worth only ≈ +₹2,400 (NIFTY) / +₹2,000 (SENSEX) under this bracket, so +₹13,452 on 1 lot needs roughly 6 or more near-perfect trades from the four days; this gate takes 2 on those days, and even the *ungated* own-scanner earns only +₹2,197 there.

**Conclusion for v1:** the research result is not reproducible with (own-scanner signals + synth ATM premium + this bracket). The most likely causes are structural, not parameter-level:
1. The research used the **broker engine's signals**, not |m5| ≥ threshold bursts (the −₹788 "identical signals" baseline can't be rebuilt without them).
2. The research's **contracts/premiums** differ (C8's 120–215 band implies higher-premium contracts than nearest-weekly ATM on Mon/Tue).
3. Possible different P&L basis (more lots, other exits) and the research doc's own date/day-count inconsistency.

## Open items → v2 candidates (nothing applied in v1)
1. Obtain the engine's actual signal list (times/direction) for Oct 6, 7, 14, 16 → "engine-gate mode", where C1 becomes meaningful.
2. Real premiums via `/charts/rollingoption` (`expiryCode: 1`) and contract selection that lands in the C8 band.
3. Prior-session lookback seeding (43/201 candidates were in the warm-up window).
4. Verify Oct 2025 lot sizes; confirm what exactly the research's P&L represents (lots, exits).
