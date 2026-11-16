# v2 — evidence-driven redesign: what the data supports

**Bottom line: no robustly profitable strategy was found. One candidate has a small, decaying, execution-sensitive edge.** Nothing here should be traded with real money before forward (paper) validation.

## Method (fixed before looking at results)
- Data: Dhan 5-min index candles, 2022-01-03 → 2026-11-13, ~1,190 sessions per index (days ≠ 75 bars excluded).
- Split: TRAIN 2022-01 → 2024-06 (≈606 days), TEST 2024-07 → 2026-11 (≈585 days). Configs selected on train only; test touched once per config.
- Signals: burst |m5| ≥ z·σ5 (σ5 = prior-5-session std of 5-min changes, no look-ahead); only bars with a full 60-min lookback (≥10:15); non-overlapping; day-clustered t-stats.
- Family: 64 configs (continuation/fade × z 2,3 × four v1-style filters) × h ∈ {3,6,12} bars × 2 indices. Files: `research/edge_study.py`, `research/option_study.py`; full tables in `edge_study_all_configs.csv`, `option_study_all_configs.csv`.

## Finding 1 — index-level edge (before options)
- **Continuation after large bursts has a short-lived edge (~15 min).** Train t 3.5–5 on both indices; test keeps the sign (NIFTY `cont|z3|T` test t = 2.6, SENSEX `cont|z2|T` t = 2.6) but shrinks (≈0.38σ → 0.15σ).
- **Fades do not survive**: at 30–60 min they flip sign or vanish out of sample.
- Edge is a 15-minute effect; **v1's SL/T1/T2 bracket (hours-long holds) was the wrong exit** — price drifts back to a random walk, leaving theta and costs.

## Finding 2 — after option costs
Long ATM CE/PE, constant-maturity Black-Scholes (DTE 4, IV 12%/13%), time exit at +15 min, −15% stop; slippage 0.3%/side NIFTY, 0.6%/side SENSEX + brokerage/STT/exchange/stamp.
- Only ~20% of all configs are net-positive after costs (train and test alike).
- **SENSEX ≈ 0 net** after its wider costs.
- **NIFTY candidate** (pre-set rule's top pick): *burst ≥ 3σ5, 60-min trend agrees, not 12:00–13:00, long ATM option in burst direction, exit after 15 min, 15% stop.*

| NIFTY candidate | Train | Test |
|---|---|---|
| Trades | 262 | 290 |
| Gross / net per trade (% of premium) | +4.7% / +3.1% | +2.8% / **+1.4%** |
| Net t-stat (day-clustered) | 3.0 | **1.45** |
| Win rate | – | 47% |

Robustness:
- Positive in **10 of 10 half-years**, but decaying: +8.4% (2022H1) → +1.6% (2023H1) → +0.7% (2025H1) → +0.25% (2026H1) → +2.75% (2026H2, 35 trades).
- Break-even at **≈2.1× my assumed costs**; at 2× costs net ≈ 0, at 3× it loses.
- Higher IV / longer DTE lowers it (DTE 6, IV 15% → +0.4%); lower IV / shorter DTE raises it.
- Test bootstrap (day blocks): mean +1.4%, 90% CI [−0.2%, +3.1%], P(≤0) ≈ 7%.
- **Execution delay kills it:** entering one bar (5 min) after the burst bar → test net +0.6% (t 0.7); two bars → −1.0%. Needs fills within seconds of the bar close.
- All data, 1 lot @ NIFTY 65: ≈ +₹80,700 over 552 trades in ~4.9 years (≈ ₹146/trade, ≈ ₹16k/yr); worst day −₹3,362; max drawdown −₹18,186 (≈ a full year of profit). Lot sizes changed over the period, so ₹ figures are illustrative; percentages are the clean metric.

## What this says about the original research claim
An edge of ~1–3% of premium per trade makes +₹13,452 in four days (≈ ₹3.4k/day) an unusual outcome under this gate — consistent with a small-sample or engine-specific result, not with a generalisable +ve expectancy. (Consistent with, not proof.)

## Limits you should weigh
- Premiums are **modelled** (Black-Scholes, fixed DTE, flat IV), not traded quotes; no bid-ask data was available. Real fills after a burst may be worse than 0.3%.
- 4.9 years includes one regime; edge decay suggests crowding/efficiency gains.
- 64×3×2 configs were examined; the headline pick was fixed by a pre-set rule, but family-wise multiple testing still applies (test t = 1.45 would not survive correction).
- Tool is read-only; the candidate is NOT wired into `backtest.py` (that still runs the v1 bracket on the 10-day sample).

## Recommended next steps (in order)
1. Paper-trade the NIFTY rule forward for ≥ 3 months, logging *actual* fill times and option quotes; compare to the 0.3%/side assumption.
2. Validate with **real** option premiums (`/charts/rollingoption`, `expiryCode 1`; fixed-strike tracking via ATM±k) to replace Black-Scholes.
3. Only if (1) and (2) hold: consider sizing and automation — which this tool deliberately does not do.
