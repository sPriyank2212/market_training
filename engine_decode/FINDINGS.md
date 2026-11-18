# Engine decode — new findings (2026-11-18)

Builds on `backtest/research/signals/RESULTS.md` (not repeated here). Data: `signals/signals.xlsx` only — 305 cards with date+time,
11 trading days, 19 Oct–13 Nov 2026 (219 NIFTY, 86 SENSEX). 1-min Dhan spot with volume, 375 bars/day, is byte-identical to the earlier study's cache.
Scripts (all in `engine_decode/`): `fetch_1m.py`, `build_signals.py`, `features.py`, `hist_test.py`, `fwd_test.py`, `direction_test.py`.
Day-level leave-one-day-out (LODO) validation throughout; **no rule below is a reproduction of the engine**.

## 1. Timing (when it fires) — still not decoded, and the evidence now points to "not a price trigger"
| Test | NIFTY | SENSEX |
|---|---|---|
| Best single 1-min spot feature, AUC (signal minute vs every other minute) | 0.61 (5-bar mean abs move) | 0.61 (position in day range) |
| Time of day alone (earlier = more likely) | **0.635** | **0.627** |
| Gradient boosting on 34 spot/volume features, LODO | 0.581 | 0.568 |
| Time + the engine's own recent-signal counts, LODO | 0.622 | **0.704** |
| Time + counts + spot features | 0.601 | 0.632 |

- 25 % of all signals fall in the first 30 minutes; rate decays through the day. Spot features add **nothing** beyond time of day (GBM is below time-only).
- Combined NIFTY+SENSEX signals per day: 22–33 (mean 27.7, sd 3.6). Gaps between consecutive signals: CV 1.10 (a memoryless process has 1.0).
- Hazard vs minutes since the previous same-index signal is flat (NIFTY 4–6.5 % per minute at every lag up to 30 min). **No cooldown / refractory period.**
- SENSEX's improvement to 0.70 comes from day-level persistence ("SENSEX is the active index today"), not from a reaction to price.
- **Which index is active follows expiry**: NIFTY 28/25/24 signals on its expiry days (19 Oct, 27 Oct, 3 Nov), SENSEX 22/18 on its expiry days (29 Oct, 5 Nov). The index with DTE 0–1 gets most signals.
- Reading: signal timing behaves like a time-varying random process (rate ↓ through the day, ↑ for the expiring index) with a direction chosen from trend, not like a deterministic price trigger. A 1-min or tick price rule is unlikely to reach recall 0.6 / precision 0.3.

## 2. Direction (CE vs PE) — partly decoded
Past-only rules, accuracy on signal rows (CE share is 64 % NIFTY / 74 % SENSEX, so the majority baseline is already that high):
| Rule | NIFTY | SENSEX |
|---|---|---|
| sign(EMA5−EMA20 of 1-min closes) | 0.75 | 0.86 |
| sign(EMA9−EMA21) | 0.73 | 0.86 |
| sign(30-min move) / position in day range | 0.75 / 0.75 | 0.82 / 0.84 |
| best depth-2 tree over any pair, LODO (selected from ~300 pairs → optimistic) | 0.82 (EMA3−9, 30-min move) | 0.87 (EMA3−9, EMA20−50) |

Direction is trend-following with ~15–20 % counter-trend signals. Day-level CE share matches the sign of the move after 10:15 on 15 of 17 index-days (contemporaneous, so partly circular).

## 3. Does the engine know the future? (forward spot move in the signal's direction, points, signal vs matched random minutes)
| | f15 signal | f15 random minute, same direction | f15 random minute, direction = prior 10-min move |
|---|---|---|---|
| NIFTY | +9.0 | +6.2 (p 0.27) | +1.4 (p < 0.01) |
| SENSEX | **+47.5** | +15.4 (p < 0.01) | −4.1 (p < 0.01) |

- The engine's **direction** beats a naive 10-min-momentum direction by a wide margin; its slow-trend direction is what carries the drift.
- **Timing** adds forward information for SENSEX (+32 pts at 15 min over same-direction random minutes) but not significantly for NIFTY.
- Not a profitability test (spot, not option P&L; 11 days; a trending, call-heavy sample).

## 4. What a replica would look like (consistent with all evidence, unproven)
Per index, each minute: fire with probability λ(time of day, expiry proximity, day activity); choose direction by slow trend (EMA / day-range position); buy the strike whose premium ≈ ₹160 NIFTY / ₹300 SENSEX; SL/T1/T2 from ₹ templates on a ₹5 grid (earlier study). The timing term is the unproven part: if the engine really uses tick data or private inputs, this cannot be distinguished from randomness with 1-min bars.

## 5. Still open
1. Tick or sub-minute data (the app likely scans faster than 1 min; minute-of-hour is uniform).
2. Whether timing is conditioned on the *option* chain at tick level (earlier study found option-bar AUC 0.60–0.67 only).
3. The 36 "Not Triggered" cards — what the entry rule is.
4. Seven trading days have no cards (probably screenshot gaps). Extra screenshots would turn each into a held-out test day.
