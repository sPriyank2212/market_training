# Strategy v1 — eight-check gate, as originally specified

Run: `BACKTEST_VERSION=v1 python backtest.py` (v1 is the default).
Files: `config.yaml` (frozen parameters), `spec.md` (frozen copy of the spec incl. the 4 rulings), `results/` (per-milestone summaries, ledger CSVs).

## Definition (what makes this v1)
- Own-scanner: candidate on every 5-min bar close with |m5| >= th_trig (NIFTY 20 / SENSEX 60).
- Eight veto checks C1–C8 with config thresholds; flip rule **disabled**.
- Features use **within-day lookbacks only**; a NaN needed by a check **fails** that check (so the first 30–60 min are partly un-tradeable: m30 NaN < 09:45, trend NaN < 10:15).
- Signal stamp = bar start (`features.signal_time: bar_start`).
- Bracket exits: SL −15%, T1 +8% (then SL→cost on remainder), T2 +25%, flat 15:15; intra-bar ties → SL first.
- Premium: Black-Scholes synth (IV 13%), ATM, 1 lot.
- One position at a time (overlapping signals are SKIPPED and logged).
- Sanity target applies only to Oct 6, 7, 14, 16: +₹13,452 ±₹250; full Oct 5–17 range reported separately.

- Spec gaps filled with explicit assumptions: T1 sells 50% (`exits.t1_fraction`); cost-stop not tested in the T1 bar; only a full `SL` exit counts toward C6; no slippage/brokerage.

## Candidate changes for v2 (NOT in v1 — do not apply here)
- Seed lookbacks from the prior session so the opening hour is tradeable (`lookback_seed: prior_session`) — 43/201 candidates fall in the warm-up window.
- Contract selection so premium sits in the C8 band (next expiry or 1-step ITM) — see M4 finding 1.
- Real option premiums (`/charts/rollingoption`, `expiryCode: 1`) and/or calibrated IV (real ≈ 8–9% vs 13% assumed).
- Lot-size correction for Oct 2025 (NIFTY 75?) once verified.

## Status
M0-M5 ✅ COMPLETE and FROZEN (see FROZEN.md). Sanity target NOT reproduced: +₹53 vs +₹13,452 — see results/M5_summary.md.
