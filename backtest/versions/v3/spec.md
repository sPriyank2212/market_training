# Kimi Code Master Prompt — Engine Signal Strategy Backtester (2026 RE-RUN)

Copy everything below the line into Kimi Code in VS Code (one message is fine; it can work through it milestone by milestone).

---

## ROLE & CONTEXT

You are building a **private, read-only backtesting tool** for an Indian index options momentum strategy (NIFTY + SENSEX, weekly options). The user runs Windows 11, Python 3.12, VS Code. Data source is the **Dhan Data API v2** (subscription active). This tool must NEVER place, modify, or cancel orders — it may only call market-data/history endpoints. Add a hard guard in code: block any URL containing `/orders`.

Strategy research summary (the "eight-check gate"): a broker signal engine fires option-buying signals on fast 5-minute momentum bursts with no market-context filter. A filter of 8 veto checks turned its 5-day P&L from −₹788 to +₹13,452 (1 lot, identical signals). Your job: replay that gate on historical 5-min candles.

### ⚠ WHY THIS IS A RE-RUN (read first)

A previous version of this pipeline was built and run — **on the wrong year**. It fetched **2025-10-05…17** candles, but the engine signals, screenshots and the +₹13,452 target are all from **October 2026** (verified: NIFTY 27 Oct 2026 = O 22708.80 / H 22829.75 / L 22636.85 / C 22749.75 matches the research tape exactly; Oct 2025 NIFTY traded ~25,000, over 2,000 points away). The previous run's "target not reproduced" conclusion is therefore invalid. Everything below is identical in logic to the reviewed, tested v1 — only the dates and the expiry handling change, plus a data-validation gate so this class of bug can never pass silently again.

**Correct trading days: 2026-10-05 (Mon), 06 (Tue), 07 (Wed), 08 (Thu), 09 (Fri), 12 (Mon), 13 (Tue), 14 (Wed), 15 (Thu), 16 (Fri).** Sanity/sample days: **2026-10-05, 06, 07, 14, 16**.

## SECURITY RULES (non-negotiable)

1. Dhan credentials come from environment variables only: `DHAN_CLIENT_ID` and `DHAN_ACCESS_TOKEN`. Load them with `python-dotenv` from a local `.env` file. NEVER hardcode tokens, never print the full token in logs (mask it), never commit `.env` (create a `.gitignore` with `.env`).
2. Read-only: only `POST https://api.dhan.co/v2/charts/*` and Dhan's expired/rolling option-history endpoints. Refuse any other path.
3. The access token expires every 24 hours — if a request returns 401/403, print a clear message: "Token expired — generate a new one at web.dhan.co → DhanHQ Trading APIs."

## MILESTONE 0 — Project scaffold

Create in the current workspace:
```
backtest/
├── .env                  # user fills in (template provided, gitignored)
├── config.yaml           # every threshold is a config value, none hardcoded
├── requirements.txt      # requests, python-dotenv, pyyaml, pandas, numpy, scipy
├── dhan_client.py        # thin API wrapper (auth headers, retries, 401 handling)
├── candles.py            # fetch + cache 5-min index candles (CSV cache per day)
├── validate.py           # data-validation gate vs Yahoo anchors (M1.5, below)
├── gate.py               # the eight-check veto gate (pure functions, unit-testable)
├── premium.py            # premium model: REAL (Dhan expired options) or SYNTH (Black-Scholes)
├── exits.py              # bracket exit simulator on the premium series
├── ledger.py             # trade/skip log writer (CSV matching the Excel tracker schema)
├── backtest.py           # main runner: days → signals → gate → entries → exits → P&L report
└── tests/
    └── test_gate.py      # unit tests for the gate (see acceptance criteria)
```

## MILESTONE 1 — Dhan connection test

Endpoint for index intraday candles (verify against docs at https://dhanhq.co/docs/ before assuming):
- `POST https://api.dhan.co/v2/charts/intraday`
- Headers: `access-token`, `client-id`, `Accept: application/json`
- Body: `{"securityId": "...", "exchangeSegment": "IDX_I", "instrument": "INDEX", "interval": "5", "fromDate": "YYYY-MM-DD", "toDate": "YYYY-MM-DD", "oi": false}`
- NIFTY index securityId and SENSEX index securityId must be resolved from the Dhan instrument master (https://images.dhan.co/api-data/api-scrip-master.csv), filtered to `SEM_EXM_EXCH_ID = "NSE"` / `"BSE"` and index names — do NOT hardcode; cache the CSV locally.

Acceptance: fetch NIFTY 5-min candles for **2026-10-06** and print the bar count (~75) and first/last timestamp. Handle weekends/holidays gracefully (Dhan returns empty or error — detect and skip).

## MILESTONE 1.5 — Data-validation gate (NEW, mandatory)

The previous run compared 2025 candles against a 2026 target and nothing caught it. Add `validate.py` and run it automatically after every fetch:

1. **Year assert (trivial, non-bypassable):** every fetched candle's date must have `year == 2026`. Fail loudly otherwise.
2. **Anchor check:** compare each fetched day's O/H/L/C against the Yahoo reference anchors below (tolerance 0.15%). Print a per-day table `date | dhan_close | anchor_close | diff% | OK/FAIL`. Any FAIL → stop and report; do not proceed to backtest.
3. **Bar-count check:** expect 75 bars/day (09:15–15:30 IST session, bar-start timestamps 09:15…15:25). Note: Yahoo itself shows 73 bars on 2026-10-15 (feed gap), so treat 73–75 as acceptable with a warning; anything else is a FAIL.

**Yahoo reference anchors (5-min bars aggregated to daily; IST):**

| Date | NIFTY O | NIFTY H | NIFTY L | NIFTY C | SENSEX O | SENSEX H | SENSEX L | SENSEX C |
|---|---|---|---|---|---|---|---|---|
| 2026-10-05 | 22532.40 | 22621.80 | 22397.50 | 22555.75 | 72340.95 | 72631.10 | 71840.18 | 72382.39 |
| 2026-10-06 | 22603.25 | 22776.10 | 22561.80 | 22776.10 | 72508.05 | 73281.85 | 72387.27 | 73067.81 |
| 2026-10-07 | 22690.45 | 22717.25 | 22546.55 | 22603.05 | 72904.52 | 73477.28 | 72468.72 | 72638.70 |
| 2026-10-08 | 22599.05 | 22599.05 | 22180.30 | 22231.80 | 72693.97 | 72693.97 | 71188.60 | 71566.40 |
| 2026-10-09 | 22316.80 | 22580.50 | 22295.20 | 22520.45 | 71776.67 | 72668.67 | 71747.82 | 72472.33 |
| 2026-10-12 | 22593.20 | 22650.55 | 22304.45 | 22363.35 | 72777.51 | 72879.78 | 71676.10 | 71924.68 |
| 2026-10-13 | 22364.15 | 22721.95 | 22288.70 | 22721.95 | 71951.73 | 73044.91 | 71712.60 | 73033.78 |
| 2026-10-14 | 22715.75 | 22757.80 | 22558.95 | 22622.70 | 73047.72 | 73193.89 | 72579.28 | 72781.89 |
| 2026-10-15 | 22671.30 | 23056.20 | 22637.40 | 22997.35 | 72964.16 | 74762.53 | 72898.67 | 74315.61 |
| 2026-10-16 | 23049.55 | 23149.85 | 22914.30 | 23146.15 | 74341.08 | 74788.79 | 74015.69 | 74729.27 |

The user also has the raw Yahoo 5-min files (`yahoo_5m_NIFTY_2026-10-05_to_16.csv`, `yahoo_5m_SENSEX_2026-10-05_to_16.csv`) — place them next to the project if a bar-level diff is ever needed.

## MILESTONE 2 — Candle cache + feature engine

For each trading day, build from 5-min closes (IST):
- `m5  = close - close_5min_ago` (per bar)
- `m30 = close - close_30min_ago`
- `rng = (close - day_low) / (day_high - day_low)` (guard divide-by-zero on dead days)
- `trend = sign(close - close_60min_ago)` (live trend, last 30–60 min)
- day open, day high, day low

Cache every downloaded day as CSV in `data/cache/` so re-runs are free.

**Warm-up policy (open data-definition decision — keep as config, do NOT tune to any target):**
```yaml
warmup:
  nan_policy: fail     # fail = a check needing a NaN value FAILS (conservative, v1 behaviour)
                       # other values for later A/B: pass | seed_prior_session
```
Lookbacks are within-day, so `m30` is NaN before 09:45 and `trend` before 10:15 (~21% of candidates). Default stays `fail`, exactly as v1.

## MILESTONE 3 — The eight-check gate (core deliverable)

Signal generation (own-scanner mode, per research doc Section 4): on every 5-min candle close, if `|m5|` crosses ≥ threshold, that's a candidate signal; direction = sign of the burst. Then apply ALL eight checks — one failed check = SKIP (a check is a veto, not a score). Thresholds are NIFTY-first / SENSEX-second, read from config.yaml:

```yaml
gate:
  th_trig:        { NIFTY: 20,  SENSEX: 60 }   # C1 signed 5-min burst in trade direction
  th_exh:         { NIFTY: 40,  SENSEX: 130 }  # C2 signed 30-min move; SKIP if >= (exhausted)
  rng_min: 0.15                                 # C4 range position window
  rng_max: 0.85
  midday_start: "12:00"                         # C5 hard kill zone, IST
  midday_end:   "13:00"
  max_consec_sl: 2                              # C6 revenge chain → 60-min timeout
  timeout_minutes: 60
  day_brake: -7000                              # C7 realised day P&L floor (₹)
  premium_band: { NIFTY: [120, 215], SENSEX: [300, 460] }  # C8, only when premium known
flip_rule:
  enabled: false    # SHIP DISABLED — provisional per research; needs forward validation
  burst:   { NIFTY: 30, SENSEX: 90 }
  life_minutes: 30
exits:
  sl_pct: 0.15        # SL at entry*(1-0.15); engine SL wins when tighter (engine mode only)
  t1_pct: 0.08        # standalone default target 1 (+8%)
  t2_pct: 0.25        # target 2 (+25%)
  t1_fraction: 0.5    # share of position sold at T1 (v1 assumption, spec silent)
  flatten_time: "15:15"
risk:
  lot_size: { NIFTY: 65, SENSEX: 20 }   # confirmed on 2026 signal cards; still read from instrument master
  max_trades_per_day: 12
mode: synth    # "synth" = Black-Scholes premium model | "real" = Dhan expired-options data
synth:
  iv: { NIFTY: 0.13, SENSEX: 0.13 }     # ATM weekly IV assumption, kept explicit
  risk_free: 0.065
entry_fill: signal_close   # premium at the signal bar's close (v1 behaviour; no slippage/brokerage)
```

Checks (signed with `sgn = +1 if CE else -1`; `sm5 = m5*sgn`, `sm30 = m30*sgn`):
- C1 trigger: `sm5 >= th_trig`
- C2 exhaustion: `sm30 < th_exh`
- C3 trend: `trend == sgn` OR flip active (flip: a burst ≥ flip.burst crossing the day open grants 30-min bias override; disabled by default)
- C4 range: `rng_min < rng < rng_max` (strict both sides)
- C5 time: blocked iff `12:00 <= t < 13:00` IST
- C6 revenge: `consecutive_sl < max_consec_sl` and not inside timeout. Only a full stop-out counts as an SL (a T1-then-cost exit does not). On the 2nd consecutive SL the 60-min timeout starts at that exit time and the chain counter resets; entry allowed at exactly +60:00, blocked at +59:59.
- C7 day brake: passes iff `day_realised_pnl > -7000` (−7000 exactly → SKIP)
- C8 contract: entry premium within band, inclusive; if mode can't supply premium, log `C8=NA` and treat as pass, visibly

State carried across signals within a day: consecutive SL count, timeout window, realised P&L, trades taken. `risk.max_trades_per_day` is an extra guard reported as `MAXTRADES` (not one of the eight). At 15:15 force-flat any open position; no entries whose bar closes ≥ 15:15. Evaluate all eight checks with no short-circuit — the ledger shows every result.

## MILESTONE 4 — Premium model

`mode: synth` (default): Black-Scholes price the weekly option at each bar using the spot path, calendar time-to-expiry, and config IV (r = 6.5%, no dividends). Contract fixed at entry from the entry-bar spot: ATM = round(spot÷50)×50 for NIFTY, round(spot÷100)×100 for SENSEX. **Dynamic ITM step (research doc Section 6):** if the ATM premium is below the C8 sanity band, step one strike ITM; never step OTM. Theta must emerge from the model as T shrinks bar by bar (no separate theta term). Per-bar premium high/low derived from the bar's spot high/low (monotone for fixed strike/T). Floor T at a `min_T_minutes` value to guard expiry-day T→0.

**Expiry resolution — do NOT hardcode a weekday (this is a change from v1):** the exchange moved expiry days during this period (NIFTY weekly expired on **Monday 2026-10-19** — a holiday-shifted expiry — and on Tuesday 2026-10-27). Resolve actual weekly expiry dates from the Dhan instrument master for each index, then assert them against these known dates for the sample window:
- NIFTY weekly expiries: **Tue 2026-10-06, Tue 2026-10-13** (then Mon 2026-10-19 — outside window)
- SENSEX weekly expiries: **Thu 2026-10-08, Thu 2026-10-15**

Expiry time 15:30 IST. Use the **nearest weekly expiry** at each entry (engine behaviour).

`mode: real`: fetch expired/rolling option history from Dhan. Known-good from a probe: `POST /charts/rollingoption` requires `expiryCode: 1` (`0` is rejected with DH-905 despite the docs), date-only `fromDate/toDate` (toDate behaves inclusively), `interval: "5"`. The rolling-ATM strike rolls with spot, so a fixed-strike position needs a multi-strike (ATM±k) fetch — if that is not implemented, fail loudly and fall back to synth with a loud WARNING.

Exits: SL −15% (never widened), T1 +8% (sell `t1_fraction`, move SL on remainder to entry cost; the cost-stop is not tested until the next bar), T2 +25%, flat 15:15. **Ties: SL fills first** (SL vs T1, SL vs T2, cost-stop vs T2). Fills at the level, no slippage, no brokerage.

## MILESTONE 5 — Ledger + report

Every candidate signal (taken OR skipped) gets one row, columns: date, time, index, contract, side, entry, lot, exit, exit_reason (T1/T2/SL/EOD), pnl, sm5, sm30, rng, C1..C8, verdict, skip_reason, mode. Save to CSV. Print a daily summary table and total P&L.

Run the five sanity days first: **2026-10-05, 06, 07, 14, 16** (skip non-trading days silently), then the full window 2026-10-05…17.

**How to read the output (important, do not mis-scope):** the +₹13,452 research figure was produced in *engine-gate mode* — the engine's actual 101 signals with actual screenshot fills. This run is *own-scanner mode* with synthetic premiums, so it is **not expected to land on +₹13,452** and must not be tuned toward it. Success here means: validation gate passes, ledger is complete, gated vs ungated control are both reported, and every number is traceable. The engine-gate A/B comes later, once the user supplies the decoded 101-signal list (keep a `mode: engine_gate` path in backtest.py that reads a signals CSV with columns date,time,index,side and runs the same gate on those rows — that mode also makes C1 meaningful instead of tautological).

If results look surprising, investigate data/fill assumptions before touching thresholds — do NOT tune thresholds to fit.

## ACCEPTANCE CRITERIA

1. `test_gate.py` proves: one failed check → SKIP with exactly its ID in skip_reason; midday signal → SKIP (incl. 12:00:00 blocked / 13:00:00 allowed boundaries); rng 0.90 → SKIP; 2 consecutive SLs → 60-min timeout (blocked 59:59, allowed 60:00); day brake at −₹7,000 stops trading (−7000 SKIPs, −6999 passes); NaN in a needed value → that check FAILS; per-index thresholds; PE sign handling; flip on/off; daily cap. Include a mutation self-check: 6 deliberate off-by-one bugs (C7 `>=`, C5 end-inclusive, C5 start-exclusive, C2 `<=`, C4 inclusive, 59-min timeout) must each be caught by the suite.
2. The validation gate runs on every fetch and its anchor table prints all-OK for the 10 trading days.
3. Full 10-day run completes offline from cache in <10 seconds.
4. Ledger CSV opens cleanly in Excel.
5. No token anywhere in code; `.env` in `.gitignore`; no order endpoints reachable.
6. Report prints: per-day P&L table, totals, TAKE/SKIP counts, most-failed check, and the gated-vs-ungated comparison.

## HOW TO WORK

Proceed milestone by milestone. After each milestone, run it, show the user the output, and wait for a "continue" before starting the next. If any Dhan endpoint differs from what's described here, check https://dhanhq.co/docs/ first and tell the user what you changed. Ask before adding any feature not listed above — especially anything that places orders.

---

# Required info / setup (for the user, not part of the prompt)

1. **`.env` file** in the `backtest/` folder:
   ```
   DHAN_CLIENT_ID=your_client_id
   DHAN_ACCESS_TOKEN=your_token
   ```
   Token expires every 24 h — regenerate at web.dhan.co → DhanHQ Trading APIs if you get 401/403.
2. **Python 3.12** with: `pip install requests python-dotenv pyyaml pandas numpy scipy`
3. **Validation files** (optional but recommended): copy `yahoo_5m_NIFTY_2026-10-05_to_16.csv` and `yahoo_5m_SENSEX_2026-10-05_to_16.csv` (delivered alongside this prompt) next to the project for bar-level diffs. The daily anchors are already embedded in the prompt.
4. **Dates are 2026, not 2025.** If any output ever shows 2025, the validation gate in M1.5 should have caught it — stop and check.
5. Known Dhan quirks from the earlier probe: rolling-option endpoint wants `expiryCode: 1` (not 0), `toDate` is inclusive, strikes roll with spot.
