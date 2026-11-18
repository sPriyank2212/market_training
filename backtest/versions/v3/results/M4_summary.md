# v3 — M4 premium model + exits (2026 data)

## Expiry resolution (change vs v1: no hardcoded weekday)
Expired contracts are not in Dhan's instrument master (it lists only future expiries: first NIFTY entry 2026-11-17), so expiries are resolved from the **trading calendar**: the index's weekly weekday, moved back to the previous trading day when that day is a holiday, then **asserted** against the known dates (mismatch raises `ExpiryAssertionError`).
- NIFTY: Tue 06-Oct, Tue 13-Oct, **Mon 19-Oct (Dussehra shift from Tue 20-Oct)**, Tue 27-Oct, Tue 03-Nov. SENSEX: Thu 08-Oct, 15-Oct, 22-Oct, 29-Oct, 05-Nov. All 6 known dates reproduced.
- Nearest weekly on/after the entry day is used (same-day expiry on expiry day). `tests/test_expiries.py` proves the holiday shift and that a wrong calendar fails the assertion.

## Dynamic ITM step (research doc §6, now implemented)
If the ATM premium at the entry bar is below the C8 band, step ONE strike ITM; never OTM (`synth.dynamic_itm: true`).
Result on the 289 candidates: ATM below band on 149 -> stepped ITM; final premium **in band 149**, **still below 116** (expiry day and 1 DTE: one step ITM is not enough, e.g. NIFTY 0 DTE median ATM 27.5), **above 24** (SENSEX 6 DTE ATM ~530 > 460). C8 therefore acts largely as a days-to-expiry filter (NIFTY passes only at 3–6 DTE; SENSEX at 2–3 DTE). `M4_c8_premium_check.csv`.

## Model checks
- Theta emerges from Black-Scholes as T shrinks (flat spot 22,500, expiry 13-Oct): ATM call 71.0 -> 67.7 -> 63.5 across 12-Oct; 31.5 -> 23.6 -> 7.2 across expiry day.
- Exits (SL-first ties, T1 half-sell then cost-stop from the next bar, T2, flat 15:15): 28 premium/exit/expiry tests pass; 85+ tests overall.
- End-to-end trade hand-check (SENSEX 05-Oct 14:10, 72300 CE): entry 379.79, SL 322.82 = entry x 0.85, exit at SL, pnl (322.82-379.79) x 20 = -1,139.36 ✓.

## Model vs reality (read-only Dhan rollingoption, ATM call, 5-min)
| | DTE | real IV | real ATM median | BS @ 13% | BS / real |
|---|---|---|---|---|---|
| NIFTY 07-Oct | 6 | 11.1 % | 151.2 | 168.0 | 1.11 |
| NIFTY 14-Oct | 5 | 11.8 % | 144.0 | 150.0 | 1.04 |
| SENSEX 07-Oct | 1 | 15.6 % | 265.0 | 222.4 | 0.84 |
| SENSEX 14-Oct | 1 | 15.9 % | 265.5 | 216.3 | 0.81 |
Synthetic premium is ~4–11 % rich for NIFTY and ~16–19 % cheap for SENSEX at the flat 13 % IV — which matters because C8 is a premium band. `mode: real` is still not implemented (multi-strike fetch); it fails loudly and falls back to synth. Not tuned: IV stays 13 % per the spec.

## Gated-run preview (NOT the M5 report): 289 candidates -> 8 TAKE after C8/OPEN/LATE; exits SL 6, T1 1, EOD 1. Full ledger and totals come in M5.
