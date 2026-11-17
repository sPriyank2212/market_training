# Signals reverse-engineering — PLAN and success criteria

Written **before** any analysis of the signals against market data (written 2026-11-16, after the data fetch was
started but before any fit/test was run). Nothing below was changed after looking at results; if something is
changed later it is appended under "Amendments" with the reason.

Goal: find the simplest rule that reproduces the AlphaEdge engine's NIFTY/SENSEX option signals, and say honestly
how well it does. **Reproducing the engine is not the same as profitability** — `backtest/SUMMARY_ALL_TESTS.md`
found no robust edge; this study does not change that.

## Data
- `signals/signals.xlsx`: 306 rows. Columns used as-is; CE/PE and strike come from `Trade`; `Side` is always BUY.
- Dhan 1-min spot (`/charts/intraday`) and 1-min rolling options (`/charts/rollingoption`, ATM±10, expiryCode 1 and 2)
  cached under `backtest/data/cache/signals/` (git-ignored). Read-only; `/orders` guard unchanged.
- Expired contracts are not in the scrip master, so option history comes only from rolling-option data
  (strikes reachable = ATM±10 per bar; expiry = nearest weekly (1) or next weekly (2)).

## Exclusions (decided up-front)
- Rows with a non-empty `Notes` (3 rows: unreadable 23750 PE 3-Nov; index inferred from strike 22850 CE 19-Oct;
  P&L corrected 22900 PE 21-Oct) are **excluded from fitting** and listed in RESULTS.md.
- Any row whose strike is > 8% from the spot at the signal minute is treated as an OCR/date error, excluded and listed.
- "Yet to Activate"/"Active" rows have no outcome → used for H1/H2 only, not H3/H5.
- A date must have a full spot session in Dhan to count as a trading day.

## Split (fixed now, not tuned)
Sorted signal days: 10-19, 10-21, 10-23, 10-27, 10-29, 10-30, 11-03, 11-04, 11-05, 11-06, 11-13.
- **Validation (never used to build a rule): 10-23, 10-30, 11-05, 11-13** (positions 3, 6, 9, 11 – spread across the period
  so validation is not a single regime).
- **Fit: 10-19, 10-21, 10-27, 10-29, 11-03, 11-04, 11-06.**
- Rules are stated, thresholds fixed on fit days, then evaluated once on validation days. No tuning on validation.

## Clock handling
Signal times are tested at offsets −2…+2 minutes (signal minute vs candle minute). The offset is chosen on **fit days
only** by H3 (entry price match) and H1 (trigger match), then frozen for validation.

## Success criteria (per hypothesis; "validation" = the 4 held-out days)
| H | What counts as reproduced | Threshold (validation days) |
|---|---|---|
| H1 trigger | A single simple rule (≤ 2 sentences, ≤ 3 parameters) fires within ±1 min of a signal | **recall ≥ 60 %**, **precision ≥ 30 %** (≤ ~2 extra firings per signal, per day on average), and AUC vs matched random minutes ≥ 0.70 with the bootstrap 95 % CI lower bound > 0.60. Direction (CE vs PE) agrees ≥ 80 % of matched firings. |
| H2 strike | A rule "strike = f(spot at signal)" | same strike in ≥ 80 % of rows; report the exact distribution of (strike − ATM)/step otherwise |
| H3 entry | Entry premium equals a defined option price (open/high/low/close/mid of a minute) | ≥ 80 % of executed rows within max(₹1, 1 %) of that price; report error distribution regardless |
| H4 levels | SL/T1/T2 derived by a stated formula | ≥ 80 % of rows reproduced within one ₹5 tick |
| H5 outcome | First-touch replay on 1-min option high/low gives the recorded status | **≥ 85 %** status agreement on executed rows; also report agreement when intra-bar order is flipped |

A hypothesis is labelled: **confirmed** (meets the threshold on validation), **partly** (fit meets it, validation does
not, or only a part of the population does), **rejected** (fails on fit too / clearly contradicted),
**cannot tell** (data missing or sample too small).

## Controls and statistics
- Random-minute controls: for each signal, draw non-signal minutes from the **same day**, same index, within ±45 min of
  the signal's time of day, excluding minutes within ±2 of any signal. 20 draws per signal, fixed seed.
- Uncertainty: bootstrap by **day** (days are the independent unit) for AUC/recall/precision; Wilson intervals for proportions.
- Rule complexity: at most 3 free thresholds; prefer 1–2 features. With ~11 days nothing finer is supportable.
- Precision/recall are always reported together with firings per day.

## Known limits (stated up front)
- ~11 days / 306 rows (219 NIFTY, 87 SENSEX): any validation estimate has wide intervals.
- Only 4 validation days; SENSEX on those days has very few signals.
- OCR-sourced data; times are displayed minutes.
- The engine may use inputs Dhan cannot give (its own indicators, order-flow, other feeds); if a rule fails, the honest
  answer is "not reproducible from price data alone".

## Amendments
_(none yet)_
