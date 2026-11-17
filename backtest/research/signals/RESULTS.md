# Reverse-engineering the AlphaEdge signals engine — RESULTS

Data: 306 OCR'd signals (303 usable), 11 signal days, 19 Oct – 13 Nov 2026; Dhan 1-minute spot, India VIX, index futures (with OI) and
real option candles (ATM±10, nearest + next weekly, with volume / OI / IV) for **all 18 trading days** in the range.
Success criteria were fixed in [PLAN.md](PLAN.md) before any fit. Fit days: 10-19, 10-21, 10-27, 10-29, 11-03, 11-04, 11-06.
Validation days (never used to choose anything): 10-23, 10-30, 11-05, 11-13.

> **Bottom line.** The generation rule was **not found**. Price, futures, VIX and option-level features do not reproduce *when* the engine fires.
> Three smaller pieces are partly explained: strike choice (≈ a premium target), the SL distance (≈ a fixed ₹ amount) and exits (replay of real candles
> agrees with the recorded status ~88 % of the time). **Reproducing the engine is not the same as profitability**; the existing backtests in `backtest/`
> found no robust edge and nothing here changes that.

## Verdict table
| H | Question | Verdict | Key number (fit → validation) |
|---|---|---|---|
| H1 | Trigger (when it fires, CE vs PE) | **Rejected** (timing) / partly (direction) | best simple rule: recall 0.35, precision 0.12 on validation (criteria: ≥0.60 / ≥0.30) |
| H2 | Strike choice | **Partly** | strike ≈ the one whose premium is closest to ₹160 (NIFTY) / ₹300 (SENSEX): within 1 step 73 % → 87 % (NIFTY); exact strike only 32 % → 36 % |
| H3 | Entry premium vs real candles | **Rejected** (no exact candle price) | best single price: within ₹1 of recorded entry 14 % → 16 %; median error ₹4.3 |
| H4 | SL / T1 / T2 derivation | **Spot-derived: rejected. Fixed-₹ templates: partly** | SL distance is ~constant in ₹ (CV 0.23 NIFTY); % of entry is not (CV 0.72) |
| H5 | Outcomes by first-touch replay | **Confirmed** (88 %; criterion 85 %) | 87.8 % → 89.4 %; intra-bar order changes 0 of 258 results |

## H1 — Trigger
Decision information = the last **closed** 1-min bar before the displayed signal minute (clock offset tested −3…+3; AUC peaks at offset 0 for the
1-min move, so the app clock matches the exchange clock to within a minute). Controls: 20 random minutes per signal, same day/index, ±45 min of the
time of day, ≥3 min from any signal. Day-bootstrap CIs.

| Feature set | NIFTY AUC (fit → val) | SENSEX AUC (fit → val) |
|---|---|---|
| Best single spot feature (move in signal direction, last 1 min / 5 min) | 0.63 (CI 0.60–0.66) | 0.60 (CI 0.53–0.67) |
| 28 spot features combined (L2 logistic, leave-one-day-out) | 0.575 → 0.61 | 0.556 → 0.65 (n_val = 32) |
| Futures momentum / futures OI / basis / India VIX | 0.61 → 0.66 (futures 5-min move) | 0.57 → 0.70 (futures 3-min move; n_val = 32) |
| Option's own premium momentum / breakout / IV change | 0.63 → 0.67 (5-min option volume ratio) | 0.62 → 0.60 |

Everything sits at AUC 0.55–0.67, well under the pre-set 0.70 with a lower CI bound above 0.60. **As a detector** (rule: fire when the 3-min move in one direction
is ≥ 5 bps for NIFTY, 5-min move ≥ 7 bps for SENSEX; thresholds chosen on fit days):

| | Recall | Precision | Random-firing precision | Firings/day vs signals/day |
|---|---|---|---|---|
| NIFTY fit / val | 0.40 / 0.35 | 0.13 / 0.12 | 0.07 | 55 / 58 vs 19–20 |
| SENSEX fit / val | 0.29 / 0.31 | 0.06 / 0.06 | 0.02 | 39 / 43 vs 8 |

A rule that fires ~3× as often as the engine to catch a third of its signals is **not a match**; it is about 2× better than random firing.

What *is* visible:
- **Direction** follows the trend: SENSEX signals agree with the EMA9/EMA21 side 93 % of the time (and VWAP/open side 85–87 %) vs a CE share of 74 %; NIFTY agrees ~70 % with the last 5-min move vs a CE share of 64 % (weak).
- **Stream structure**: median gap between same-index signals 11 min (NIFTY) / 14 min (SENSEX); 23 of 284 within 1 min; 129 signals repeat a contract already signalled that day; the index that expires that day gets most of the signals (e.g. 19 Oct and 27 Oct NIFTY, 29 Oct SENSEX).
- Signals at 09:15–09:17 exist (no look-back possible), so the engine does not need a lookback window.

## H2 — Strike
Distance from ATM is spread (NIFTY −3…+4 steps, median +1 ITM; SENSEX wider). A fixed ITM offset gets only 20–26 % exact. A **premium target** does better:
choose the strike (ATM±10 ladder at the decision bar) whose premium is closest to P, P fixed on fit days:

| | P | exact strike (fit / val) | within 1 step (fit / val) | premium of chosen strike p10/p50/p90 |
|---|---|---|---|---|
| NIFTY | ₹160 | 32 % / 36 % | 73 % / 87 % | 79 / 157 / 194 |
| SENSEX | ₹300 | 32 % / 33 % | 54 % / 57 % | 103 / 300 / 430 |

A BS-delta target (≈0.5) is worse (exact 24–29 %). This explains why entry premiums look "banded" and why ATM drifts ITM on expiry day (the ATM premium is below the target).
Exact-strike criterion (≥80 %) **not met**; the premium-band idea is real but not precise. SENSEX validation has only 30 rows.

## H3 — Entry premium and clock
Recorded entry lies inside the [low, high] of the signal-minute option bar for 60 % of rows (fit 61 %, val 56 %); 88 % if the window is T−1…T+5. No single candle price matches:
best is the prior bar's high (within ₹1 for 14 %, within 1 % for 23–30 %, median |error| ₹4.3, p90 ₹13.6; fit and validation alike). The entry is on average **₹2.7 above** the last closed bar's close
(70 % of rows above), so it behaves like a tick price a few seconds into/after the minute (or from a different feed) rather than an OHLC value. **Cannot reproduce exactly; no clock offset improves it.**

## H4 — SL / T1 / T2
- Levels are on the ₹5 grid (SL 98.6 %, T1 98.3 %, T2 99.3 %) while entry premiums are on a ₹0.05 grid ⇒ levels come from a rounded computation, not from entry × a %.
- Not fixed percentages: SL distance as % of entry has CV 0.72 (NIFTY) / 0.91 (SENSEX); in ₹ it is much tighter: **CV 0.23 / 0.27**. NIFTY SL distance clusters at **₹20, ₹30, ₹35** (≈ 50/54/52 of 188 trades), SENSEX at **₹40–45**.
  T1 distance is mostly ₹10–25 and T2 varies. 53 different (SL, T1, T2) distance triples for NIFTY; the top 8 cover 65 %.
- **Spot-derived hypothesis rejected**: implied spot distance (premium distance ÷ delta) is not on a round-point grid, and correlation with recent swing high/low, 5/15/30-min ATR and day range is |r| ≤ 0.33 (mostly ≈ 0) on both fit and validation.
  Which of the ₹20/30/35 templates is used is not explained by day, days-to-expiry, hour, premium level or IV (tabulated; no pattern).
- Criterion (formula reproducing ≥ 80 % within a ₹5 tick) **not met**.

## H5 — Outcomes
Replay: entry bar = first bar (from the signal minute, up to 15 min) whose range contains the recorded entry (±₹0.5); then first touch of SL / T1 / T2 on 1-min highs/lows; scan from the bar after entry (variant A) or including it (B).

| | all | fit | val |
|---|---|---|---|
| Agreement with recorded status (A) | 88.4 % | 87.8 % (n=164) | 89.4 % (n=94) |
| Agreement (B) | 87.6 % | 87.2 % | 88.3 % |

Of 258 executed rows: 167 of 182 recorded "Target 1 Hit" reproduce; 55 of 70 recorded "SL Hit" (7 show a target first, 2 a T2, 6 never reach the entry price within 15 min);
9 recorded target hits never touch the entry price in the window. **Order of touches inside one 1-minute bar changes 0 of 258 results** (SL-first vs T1-first). "Target Hit" (3 rows) = exit at T2.
**Not Triggered (36 rows; 31 with option data)**: the app recorded no entry. The price in the signal minute sits at a very different place inside the displayed SL–T1 range (median 0.51, 10–90 % −0.98…0.89) than executed entries do (median 0.69, tight), and the option usually *did* rally afterwards (median +21 % in 30 min), so a simple "buy-stop never reached" does not explain them. **Cannot tell.**
Caveat: H5 uses the recorded entry and levels as inputs; it tests that the engine's exits are consistent with real prices (they mostly are, and exits are idealised at the exact level), not that the engine can be reproduced.

## Best reproduction rule
**None found.** The partial description that survives validation is:
> "Fire on a short-term move in the direction of the intraday trend (EMA9 > EMA21 → CE), buy the strike whose premium is ≈ ₹160 (NIFTY) / ₹300 (SENSEX), SL ≈ ₹20–35 (NIFTY) / ₹43 (SENSEX) below entry, T1 ≈ ₹10–25 above, T2 further out, all on a ₹5 grid."
It does **not** say *when* to fire (precision 0.12, recall 0.35) and is not a trading rule.

## Signals the rule cannot explain (`out/per_signal_verdicts.csv`)
- **Timing**: ~64–66 % of signals are missed by the best trigger rule, and the rule fires about 3× (NIFTY) and 5× (SENSEX) as often as the engine. Likely reasons: the engine uses inputs we do not have (its own indicators/scoring, order flow, other feeds), a cooldown/state machine (129 repeated contracts), or tick-level timing.
- **Not Triggered (36)** and **16 "no entry"** rows: entry price never reached in the replay window; possibly a limit/stop-limit entry with a rule we cannot see.
- **30 status disagreements** (16 where the entry price is never reached in the window, 14 where the first touch differs, e.g. recorded SL but replay shows a target): likely tick-vs-minute differences or the app's price feed.
- **Excluded from fitting (3)**: NIFTY 23750 PE (3 Nov, no date/entry); NIFTY 22850 CE (19 Oct 14:47, index inferred from strike); NIFTY 22900 PE (21 Oct 11:36, P&L corrected from OCR).
  Two NIFTY rows have strikes ≈4 % from spot (22150 PE on 30 Oct, 22850 CE on 4 Nov; both Not Triggered) and look like possible OCR errors; kept but flagged.

## Data limits and caveats
- Only 11 of 18 trading days contain signals. The seven empty days (e.g. 22 Oct, a SENSEX expiry day) are most likely **screenshot gaps**, not engine silence, so they cannot be used as negative evidence.
- 20 Oct and 10 Nov are exchange holidays (no Dhan session), consistent with weekly expiries shifted to 19 Oct / 9 Nov. All 11 signal dates are real trading days. One NIFTY row shows the Nov monthly expiry (23 Nov) on 29 Oct; kept.
- 303 usable signals over 11 days: validation = 4 days (79 NIFTY, 32 SENSEX signals); intervals are wide and several validation figures (SENSEX especially) are indicative only. No thresholds were tuned on validation days.
- Dhan rolling data gives ATM±10 only, nearest and next weekly. Expired contracts are not in the instrument master. 3 trades (strike outside ±10) have no option candles; the 504 empty files are all next-weekly (code 2) requests where that expiry did not exist.
- Option and index prices are Dhan's; the app may use another feed, which would explain the ₹4 entry errors and some outcome disagreements.
- Tokens were never printed; the client ID was printed once by an unmasked `__repr__` early in the session (since fixed, 68 tests still pass).

## Re-running
`cd backtest/research/signals` then: `python fetch_data.py` (spot + options) → `python fetch_extra.py` (VIX, futures) → `h1_*.py`, `h2_strike.py`, `h2_premium.py`, `h3_entry.py`, `h3_best.py`, `h4_levels.py`, `h4_spot.py`, `h5_outcomes.py`, `final_lists.py` → `python plot_days.py`, `python build_interactive.py` (open `out/charts/interactive.html`).
Cached data lives in git-ignored `backtest/data/cache/signals/`; do not commit raw screenshots.
