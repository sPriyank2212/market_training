# v3 — M1.5 data-validation gate

Implemented `validate.py` (year assert, Yahoo anchor check at 0.15 %, bar-count check) + 6 tests. Year assert passes (every candle is 2026).
Result on the 10 trading days (5–16 Oct 2026), 20 day-symbol rows, from cache: **all 75 bars**, **all NIFTY rows OK** (worst O/H/L/C diff 0.067 %), **SENSEX: 4 FAIL** — 06-Oct high (0.292 %), 07-Oct high (0.624 %), 08-Oct low (0.195 %), 15-Oct high (0.578 %). 05-Oct SENSEX close differs 0.097 % (passes).
Per spec, any FAIL stops the run: **backtest NOT started.**

Diagnosis (no thresholds changed): on the failing days Dhan's SENSEX/NIFTY ratio at the extreme equals the ratio of the closes (e.g. 3.2142 vs 3.2137 on 07-Oct) while the Yahoo anchor implies 3.2344 — i.e. Dhan's SENSEX range is consistent with NIFTY and Yahoo's SENSEX high looks like a spike (06-Oct +214 pts, 07-Oct +458 pts, 15-Oct +432 pts above every Dhan bar). Closes match exactly on 9 of 10 days. Not proven without the raw Yahoo 5-min files (not in the project folder).
Files: `M1_5_anchor_check.csv`.

## Update — bar-level diff against the raw Yahoo 5-min files (user supplied)
Files: `M1_5_bar_diff_NIFTY.csv`, `M1_5_bar_diff_SENSEX.csv` (every bar, Dhan vs Yahoo).
- Bars: Dhan 75/day; Yahoo 748 total (two 5-min gaps on 2026-10-15 at ~11:30–11:50, the known Yahoo feed gap). Every Yahoo bar exists in Dhan.
- **NIFTY:** all 748 matched bars within 0.087 % on every field. No failures.
- **SENSEX bars 09:15 – 15:15 (728 bars):** max difference in any field 0.114 %; **0 bars above the 0.15 % tolerance.**
- **SENSEX 15:20 and 15:25 bars (20 bars):** 16 above tolerance (max 1.14 %). **All 4 anchor FAILs come from these two bars** (day high/low/close aggregates include them).
- Dhan's 15:20 bar is completely flat (O=H=L=C = the 15:15 close) on **10 of 10 days for both NIFTY and SENSEX** — a Dhan data artefact (no ticks in that bar). Yahoo's 15:20 SENSEX bar has a real range, but its SENSEX/NIFTY ratio at 15:20 is erratic (e.g. 3.2232 vs 3.2109 at 15:15 on 06-Oct), so Yahoo's late bars are not clean either. At 15:25 both agree on the ratio.
- **Relevance to the strategy:** positions are flattened at 15:15 and no entry whose bar closes at or after 15:15 is allowed, so bars 15:20/15:25 never influence a trade or a gate input.
- Gate decision pending: user to choose between keeping the anchor check strict (backtest stays blocked) or validating the trading window (bars up to 15:15) strictly and reporting the 15:20/15:25 mismatch as a warning.

## FINAL (option 1 chosen by the user, 2026-11-18): trading-window validation
`validate.py` now validates STRICTLY every bar with start <= 15:15 (each O/H/L/C within 0.15 %, plus the window day O/H/L/C) against the raw Yahoo files; the 15:20/15:25 bars are a visible WARNING. Year assert and bar-count check unchanged; the full-day anchor table is informational when the raw Yahoo file exists (strict if it does not). backtest.main runs the gate every time and exits with code 2 if it fails.
Result (20 day-symbol rows): **OK 11 | WARN 9 | FAIL 0**. NIFTY 10/10 OK. SENSEX 9 WARN (late bars differ; 13-Oct fully OK). Worst strict-window figures: max single bar 0.114 %, window aggregate 0.114 % (both < 0.15 %). `M1_5_validation_final.csv`. **GATE: PASS — backtest may proceed.** 78 tests pass (4 new for the window rule, incl. the 15:15 boundary).
