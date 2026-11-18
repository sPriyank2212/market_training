# Kimi Code Master Prompt — Engine Strategy Decode (v2, corrected to the real data)

Copy everything below the line into Kimi Code in VS Code. Work milestone by milestone; show output and wait for "continue".

---

## ROLE & CONTEXT

You are reverse-engineering a broker's option-buying signal "engine" (NIFTY/SENSEX weekly options) from captured trade cards. Windows 11, Python 3.12+, VS Code.
**Read-only forever:** never place/modify/cancel orders; block any URL containing `/orders`; Dhan credentials only from `backtest/.env` (`DHAN_CLIENT_ID`, `DHAN_ACCESS_TOKEN`; the token expires every 24 h); never print the token or client id.

### The ONLY signal source
`signals/signals.xlsx` (sheet 1, 306 rows). It is the complete OCR decode of every SignalsFeed screenshot. **No other signal file exists** — there is no `engine_signals_master_log.xlsx`, there are no SignalsFeed PNGs and no screenshots for 5–16 Oct in the workspace (the `Screenshot 2026-09-0x.png` files are unrelated). Do not look for them, do not re-OCR anything.
- Columns: `Index, Trade, Date, Time, Entry Premium, Exit Premium, Target 1, Target 2, Premium SL, Side, Expiry, Lot, P&L (Rs), P&L (%), Status, Source, Notes`.
- `Trade` = "<strike> <CE|PE>"; `Side` is always BUY. Status: Target 1 Hit 188, SL Hit 71, Not Triggered 36, Target Hit (= exit at T2) 3, Active 3, EOD Close 3, Yet to Activate 1.
- Usable: **305 cards with date+time, 11 trading days** (19, 21, 23, 27, 29, 30 Oct; 3, 4, 5, 6, 13 Nov 2026), 219 NIFTY / 86 SENSEX, 22–33 cards per day combined. 7 other trading days in the range have no cards — probably screenshot gaps, **never use them as negative evidence**.
- Exclude from fitting (listed in `Notes`): NIFTY 23750 PE 3-Nov (no date/entry); NIFTY 22850 CE 19-Oct 14:47 (index inferred); NIFTY 22900 PE 21-Oct (P&L corrected). Two NIFTY rows have strikes ≈4 % from spot (22150 PE 30 Oct, 22850 CE 4 Nov, both Not Triggered): possible OCR errors, flag them.
- `engine_decode/build_signals.py` already writes `engine_decode/data/signals_clean.csv` (ts, date, time, index, strike, opt, expiry, lot, entry, sl, t1, t2, exit, pnl, pnl_pct, status). Reuse it.

### Data already in the workspace (do not refetch)
- 1-min Dhan index candles WITH volume (375 bars/day, 09:15–15:29), NIFTY+SENSEX, 12 Oct–13 Nov 2026: `backtest/data/cache/signals/spot_{SYM}_{day}.csv`, also `engine_decode/data/c1m/` (byte-identical for the signal window). 20 Oct and 10 Nov are exchange holidays.
- Real 1-min option candles (rolling ATM±10, nearest + next weekly; open/high/low/close/iv/volume/oi/spot), India VIX, index futures with OI — same cache folder, all 18 trading days in 19 Oct–13 Nov.
- Loaders and fixed validation split: `backtest/research/signals/common.py`, `PLAN.md`. **Validation days (never tune on them): 23 Oct, 30 Oct, 5 Nov, 13 Nov. Fit days: 19 Oct, 21 Oct, 27 Oct, 29 Oct, 3 Nov, 4 Nov, 6 Nov.** With so few days, also report leave-one-day-out (LODO) numbers.
- Do not touch `gate.py` or the eight-check gate; this project decodes the ENGINE, not our filter.

### What is already established (build on it — do not re-derive)
From `backtest/research/signals/RESULTS.md` and `engine_decode/FINDINGS.md`:
1. **Timing is NOT a price/volume/VIX/futures trigger at 1-min resolution.** Best single feature AUC ≈0.61; 28–34 combined spot features, LODO gradient boosting: 0.58 NIFTY / 0.57 SENSEX — **below time-of-day alone (0.635 / 0.627)**. Best rule: recall 0.35 / precision 0.12 (fires 3–5× as often as the engine). Option-premium momentum / volume ratio / IV change: AUC 0.60–0.67.
2. **Stream structure**: ~28 cards/day combined (sd 3.6); 25 % of cards in the first 30 min, decaying through the day; inter-signal gap CV 1.10 (≈ memoryless); hazard vs minutes-since-last same-index signal is **flat** (no cooldown); minute-of-hour uniform (not 5-min-close driven). The index that expires that day (DTE 0–1) gets most cards (NIFTY 24–28 on its expiry days; SENSEX 18–22 on its). 129 cards repeat a contract already signalled that day.
3. **Direction**: trend-following. sign(EMA5−EMA20 of 1-min closes) = 75 % NIFTY / 86 % SENSEX (CE share is 64 % / 74 %, the majority baseline). Best 2-feature tree LODO ≈ 82 % / 87 %. ~15–20 % counter-trend.
4. **Forward information**: direction is informative (signal-direction forward 15-min spot move NIFTY +9 pts, SENSEX +47 pts vs ≈0 for a naive 10-min-momentum direction); timing adds forward information for SENSEX (+32 pts over same-direction random minutes, p<0.01) but not significantly for NIFTY.
5. **Strike** ≈ the strike whose premium is closest to ₹160 (NIFTY) / ₹300 (SENSEX): within 1 step 87 % (NIFTY val) / 57 % (SENSEX val), exact 36 % / 33 %. BS-delta target is worse.
6. **Levels**: SL/T1/T2 are on a ₹5 grid (98–99 %) while entries are on a ₹0.05 grid → not entry×%. SL distance ≈ fixed ₹ (CV 0.23 NIFTY, 0.27 SENSEX; NIFTY clusters at ₹20/30/35, SENSEX ₹40–45), but **a spot-derived formula was rejected** (|r| ≤ 0.33 with ATR/swing/day range). Which template is used is unexplained. Do NOT call them simply "fixed templates" — test both ₹-template and level-from-option-price models.
7. **Entry premium** matches no single option-bar price (median error ₹4.3; entry is on average ₹2.7 above the last closed bar's close) → looks like a tick price.
8. **Outcomes**: first-touch replay on 1-min option high/low reproduces recorded status 88 % (val 89 %); exits are idealised (exact level, no slippage). Win rate 72.5 % at avg win ₹820 / avg loss −₹1,585 (break-even ≈66 %).

Hence the central open question is not "which price rule fires" but **"is the timing generated by something other than 1-min market data?"** Treat a negative result as a valid, valuable answer.

## MILESTONE E0 — Ground the dataset (small)
1. Run/verify `build_signals.py`; print per-day × index counts and the exclusion list above. Confirm the 11 dates and that 20 Oct / 10 Nov have no session.
2. Add `dte` (expiry − date, using the card's `Expiry`), `dow`, minute-since-open, and an `is_expiring_index_today` flag. Note the 29-Oct NIFTY card with expiry 23-Nov (monthly) — keep, flag.
3. Do not create any "5–16 Oct" file; `engine_gate` backtest mode stays blocked for lack of a 5–16 Oct list. State this once, plainly.

## MILESTONE E1 — Timing as a point process (core)
The old framing (binary classifier per bar) is saturated. Instead fit and compare **generative models of the card stream per index per day**, scored by out-of-sample (LODO) log-likelihood and by an AUC against all other minutes:
1. Inhomogeneous Poisson: λ(t) = f(minutes since open) only (histogram / spline). This is the baseline everything must beat.
2. + expiry proximity (DTE bucket), + day-level activity (prior-day realised range, VIX level, gap size) — pre-open-known inputs only.
3. + causal intraday state: rolling realised vol (5/15 min), |move| in the last 1–5 min, volume ratio, distance from day high/low, option volume ratio. Report incremental log-likelihood per feature group with day-bootstrap CIs.
4. Self-excitation (Hawkes) vs flat hazard: confirm or refute the "no cooldown" finding, and test whether CE and PE cards excite each other.
5. Over-dispersion test: day-level count variance vs Poisson; does 'cards per day per index' scale with realised range or VIX?
Verdict per index: does any price/volume/option feature add significant out-of-sample likelihood over time-of-day + expiry? If not, say so.

## MILESTONE E2 — Sub-minute timing and clock check
1. Minute-of-hour/second structure: card minute vs bar close; test −3…+3 minute clock offsets on the option-entry match and on the move-in-direction AUC (earlier study found offset 0 best for 1-min move).
2. Does the card minute relate to option 1-min bar timing (volume spikes, first tick of a new price level) rather than the index? Test option-bar events (new high of the last N min, volume > k×avg, IV jump) at offsets 0/+1.
3. If tick/second data is the only thing that could resolve the timing, state exactly what to capture (tick data for the signalled option, 30 minutes either side, ≥2 days) — do not invent it.

## MILESTONE E3 — Direction model
1. From the rules in finding 3, build the best **causal** direction rule per index with ≤3 parameters; select features on fit days, report validation + LODO accuracy against the CE-share baseline. Features: EMA pairs (3/9, 5/20, 9/21, 20/50), day-open and previous-close side (need prior day: use the 12–16 Oct cache), VWAP/typical-price side, day-range position, 15/30/60-min move, futures basis/OI change, VIX change.
2. Analyse the ~15–20 % counter-trend cards: are they mean-reversion after extension (distance from day high/low, 30-min move ≥ X), at a particular time, on a particular side, mostly expiry days? A table, not prose.
3. Same-contract repeats (129): what separates "repeat" from "new strike"? Time since the previous card's exit (replay it), previous result (SL vs T1), or spot distance from the strike?

## MILESTONE E4 — Contract, bracket and expiry model
1. Strike: compare premium-target (fit P per index), ATM±n, fixed-delta, max-OI. Report exact / within-1-step and MAE in strikes, per DTE bucket (expiry-day ATM premium is below ₹160, so ITM drift is expected).
2. Entry: tick-price hypothesis — entry ≈ last close + small premium; model it as function of the previous bar's range/close and test whether the 36 "Not Triggered" cards are limit/stop entries (position of entry level inside SL–T1 range, subsequent price path).
3. SL/T1/T2: fit **both** a ₹-template model (modes per index per week; quantify the looser drift across weeks) and a model with levels derived from the option's own recent range / IV-based expected move rounded to ₹5. Report % of cards reproduced within one ₹5 tick for each; criterion ≥80 %.
4. Expiry: verify every card's expiry against the actual calendar. NIFTY expiries are shifted (e.g. Monday 19 Oct, Monday 9 Nov because of holidays) — never assume weekdays.

## MILESTONE E5 — Replay fidelity (88 % → ≥90 %)
Replay every executed card on real option 1-min candles using the decoded contract + levels. Report % reproducing status (SL / T1 / T2 / EOD / Not Triggered), entry and exit premium MAE, and bucket every mismatch (entry timing, tick-vs-bar, strike mismatch, feed difference, bad OCR read). Replay does not need the trigger.

## MILESTONE E6 — Data-needs verdict
Write `engine_decode/data_needs_verdict.md`. One decisive test per dataset, verdict NEED / NICE / NO, with the number:
| Dataset | Decisive test |
|---|---|
| Tick / sub-minute data for signalled options | Only if E1 shows timing is not explained by time + expiry + 1-min features; define the minimum capture |
| India VIX (daily/intraday) | Incremental E1 log-likelihood; correlation of daily card count with VIX |
| Option OI / max-OI | Does max-OI beat premium-target for strike? (E4) |
| Greeks | Any sign the engine conditions on them? (fixed-₹ levels argue no) |
| More screenshots (the 7 empty days) | They convert fit days into held-out days; say how much the CIs would tighten |

## ACCEPTANCE CRITERIA
1. Uses only `signals/signals.xlsx`; nothing invented or re-OCR'd; the 305/11-day limits and the 7 missing days stated up front.
2. Every claim carries LODO or validation-day numbers plus a day-bootstrap interval; no tuning on 23 Oct / 30 Oct / 5 Nov / 13 Nov.
3. E1 gives a plain verdict: timing explained / not explained by time-of-day + expiry + market features.
4. Direction rule and replay fidelity reported against baselines (CE share; 88 %).
5. Read-only preserved; no tokens in code or logs; everything cached for offline re-runs.

## HOW TO WORK
Do not tune toward the +₹13,452 research figure or toward profitability. Reproducing the engine is not the same as an edge; the earlier backtests found no robust edge. Report negatives plainly — "the timing is not in 1-min market data" is a result, not a failure. Keep each milestone's output to tables, then wait for "continue".
