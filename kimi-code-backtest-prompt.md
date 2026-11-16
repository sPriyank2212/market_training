Kimi Code Master Prompt — Engine Signal Strategy Backtester
Work through this milestone by milestone (M0→M5). After each milestone, run it, show me the output, and wait for me to say "continue" before starting the next. If any Dhan endpoint differs from what's described here, check https://dhanhq.co/docs/ first and tell me what you changed. Ask before adding any feature not listed below — especially anything that places orders.
IGNORE any material about 220-EMA, NASDAQ, or "1% Club" strategies in this workspace or chat history — it is unrelated to this project.
ROLE & CONTEXT
You are building a private, read-only backtesting tool for an Indian index options momentum strategy (NIFTY + SENSEX, weekly options). The user runs Windows 11, Python 3.12, VS Code. Data source is the Dhan Data API v2 (subscription active). This tool must NEVER place, modify, or cancel orders — it may only call market-data/history endpoints. Add a hard guard in code: raise an error before any network call if the URL contains /orders.
Strategy research summary (the "eight-check gate"): a broker signal engine fires option-buying signals on fast 5-minute momentum bursts with no market-context filter. A filter of 8 veto checks turned its 5-day P&L from −₹788 to +₹13,452 (1 lot, identical signals). Your job: replay that gate on historical 5-min candles and reproduce/validate the result.
SECURITY RULES (non-negotiable)
Dhan credentials come from environment variables only: DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN. Load with python-dotenv from a local .env file. NEVER hardcode tokens, never print the full token in logs (mask it), never commit .env (create .gitignore containing .env).
Read-only: only POST https://api.dhan.co/v2/charts/* and Dhan's expired/rolling option-history endpoints. Refuse any other Dhan path. (The only other permitted network read is the agreed one-off Yahoo Finance 5-min fallback loader described in M1, GET-only, never routed through dhan_client.)
The access token expires every 24 hours — if a request returns 401/403, print exactly: "Token expired — generate a new one at web.dhan.co → DhanHQ Trading APIs."
MILESTONE 0 — Project scaffold
Create in the current workspace:
backtest/
├── .env                  # user fills in (template provided, gitignored)
├── .env.example          # empty DHAN_CLIENT_ID / DHAN_ACCESS_TOKEN template (committed)
├── config.yaml           # every threshold is a config value, none hardcoded
├── requirements.txt      # requests, python-dotenv, pyyaml, pandas, numpy, scipy, pytest
├── dhan_client.py        # thin API wrapper (auth headers, retries, 401 handling, /orders guard)
├── candles.py            # fetch + cache 5-min index candles (CSV cache per day)
├── gate.py               # the eight-check veto gate (pure functions, unit-testable)
├── premium.py            # premium model: REAL (Dhan expired options) or SYNTH (Black-Scholes)
├── exits.py              # bracket exit simulator on the premium series
├── ledger.py             # trade/skip log writer (CSV matching the Excel tracker schema)
├── backtest.py           # main runner: days → signals → gate → entries → exits → P&L report
├── .gitignore            # contains .env, data/cache/, __pycache__/
├── data/cache/           # per-day CSV candle cache (gitignored)
└── tests/
    ├── test_gate.py      # unit tests for the gate (see acceptance criteria)
    ├── test_exits.py     # bracket exits incl. intra-bar SL-first tie-break
    ├── test_premium.py   # Black-Scholes sanity (delta ≈ 0.5, theta visible)
    └── test_security.py  # /orders guard, token masking, 401 message
MILESTONE 1 — Dhan connection test
Endpoint for index intraday candles (verify against https://dhanhq.co/docs/ before assuming):
POST https://api.dhan.co/v2/charts/intraday
Headers: access-token, client-id, Accept: application/json
Body: {"securityId": "...", "exchangeSegment": "IDX_I", "instrument": "INDEX", "interval": "5", "fromDate": "YYYY-MM-DD", "toDate": "YYYY-MM-DD", "oi": false}
NIFTY and SENSEX index securityIds must be resolved from the Dhan instrument master (https://images.dhan.co/api-data/api-scrip-master.csv), filtered for index rows — do NOT hardcode; cache the CSV locally.
Acceptance: fetch NIFTY 5-min candles for 2025-10-06 and print the bar count (~75) and first/last timestamp. Handle weekends/holidays gracefully (empty/error → detect and skip).
Fallback (agreed): if this call fails or returns empty (e.g. Dhan won't serve that historical depth), do NOT burn time debugging. Load those sample days from Yahoo Finance 5-min (^NSEI for NIFTY, ^BSESN for SENSEX) into CSVs in the file-based CandleSource and proceed. The sanity check stays valid because the original research used Yahoo for those days. Tell me which source each day used. If a date is older than Yahoo's 5-min lookback window, say so and ask me for a CSV.
Token hygiene: the old access token was exposed in plaintext (live_api.txt) and is being rotated by the user; use only the fresh token in backtest/.env. Never read, print, or copy live_api.txt.
MILESTONE 2 — Candle cache + feature engine
For each trading day, from 5-min closes (IST):
m5  = close - close_5min_ago
m30 = close - close_30min_ago
rng = (close - day_low) / (day_high - day_low) (guard divide-by-zero)
trend = sign(close - close_60min_ago)
day open, day high, day low
Cache each downloaded day as CSV in data/cache/ so re-runs are free. Also pre-wire a file-based CandleSource (read local CSVs) as a fallback for days the Dhan API can't reach.
MILESTONE 3 — The eight-check gate (core deliverable)
Signal generation (own-scanner mode): on every 5-min candle close, if |m5| ≥ trigger threshold that's a candidate; direction = sign of the burst. Apply ALL eight checks — one failed check = SKIP. A check is a veto, not a score; no partial credit. Thresholds NIFTY/SENSEX from config.yaml:
gate:
  th_trig:        { NIFTY: 20,  SENSEX: 60 }   # C1: signed 5-min burst in trade direction
  th_exh:         { NIFTY: 40,  SENSEX: 130 }  # C2: SKIP if signed 30-min move >= this
  rng_min: 0.15                                 # C4 range window
  rng_max: 0.85
  midday_start: "12:00"                         # C5 hard kill zone, IST; blocked iff midday_start <= t < midday_end
  midday_end:   "13:00"                         # exclusive: a signal stamped 13:00:00 is allowed
  max_consec_sl: 2                              # C6 revenge chain → 60-min timeout
  timeout_minutes: 60
  day_brake: -7000                              # C7 realised day P&L floor (₹); pass iff pnl > day_brake (strict)
  premium_band: { NIFTY: [120, 215], SENSEX: [300, 460] }  # C8, per-index, CE or PE
flip_rule:
  enabled: false    # SHIP DISABLED — provisional per research; needs forward validation
  burst:   { NIFTY: 30, SENSEX: 90 }
  life_minutes: 30
exits:
  sl_pct: 0.15        # SL = entry*(1-0.15); never widened
  t1_pct: 0.08        # T1 = entry*1.08; on T1 fill, SL on remainder → entry (cost)
  t2_pct: 0.25        # T2 = entry*1.25
  flatten_time: "15:15"
  intrabar_tiebreak: sl_first   # if one 5-min bar spans SL and T1 (or SL and T2), SL fills first (conservative)
risk:
  lot_size: { NIFTY: 65, SENSEX: 20 }   # verify from instrument master
  max_trades_per_day: 12
sanity:
  # Research doc's actual trading days — the ONLY days compared against the target.
  days: ["2025-10-06", "2025-10-07", "2025-10-14", "2025-10-16"]
  gate_target: 13452
  engine_raw_target: -788
  tolerance: 250
mode: synth    # "synth" = Black-Scholes | "real" = Dhan expired-options data
synth:
  iv: { NIFTY: 0.13, SENSEX: 0.13 }     # ATM weekly IV assumption, explicit
  risk_free: 0.065
Checks (signed: sgn = +1 if CE else -1; sm5 = m5*sgn; sm30 = m30*sgn):
C1 trigger: sm5 >= th_trig  (NOTE: in own-scanner mode C1 is tautological — candidates are already generated by |m5| >= th_trig — so it never produces a SKIP there. This is expected, not a bug. C1 exists for engine-gate mode, where the engine's burst and the trigger re-check are decoupled. Still implement and unit-test it as a pure function.)
C2 exhaustion: sm30 < th_exh  — i.e. SKIP when the signed 30-min move in trade direction is ≥ 40/130 (firing into a building 30-min move). This is NOT trend agreement.
C3 trend: trend == sgn OR flip active (flip: burst ≥ 30/90 crossing day open grants 30-min bias override; disabled by default)
C4 range: rng_min < rng < rng_max
C5 time: blocked window is 12:00 <= time < 13:00 (exact expression). Signal at 12:00:00 → inside → SKIP; signal at 13:00:00 → outside → allowed.
C6 revenge: consecutive_sl < 2 and not inside timeout
C7 day brake: pass iff day_realised_pnl > -7000 (strictly greater). Brake trips (SKIP) when day_realised_pnl <= -7000, i.e. at exactly −₹7,000 the signal is SKIPPED.
C8 contract: entry premium within band — same band for CE and PE, per index. If mode can't supply premium: log C8=NA, treat as pass, visibly.
State carried across signals within a day: consecutive SL count, timeout window, realised P&L, trades taken. At 15:15 force-flat any open position at that bar's price.
MILESTONE 4 — Premium model
mode: synth (default): Black-Scholes price the ATM (or 1-step ITM per config) weekly option at each bar using the spot path, calendar time-to-expiry (configurable weekly expiry day; guard expiry-day T→0), and config IV. Theta must emerge from the model — do NOT subtract a separate theta term. Entry premium = premium at the signal bar close (approximate MARKET fill). Exits checked bar-by-bar on the premium series with the exact bracket: SL = entry×0.85; T1 = entry×1.08 then SL→cost on remainder; T2 = entry×1.25; force-flat 15:15. Intra-bar tie-break: if a single 5-min bar's range spans both the SL level (0.85×) and T1 (1.08×) — or SL and T2 — the SL fills first (conservative default, config: exits.intrabar_tiebreak = sl_first). After T1 fills, the same rule applies to the remainder (cost-SL vs T2 in one bar → SL/cost first).
mode: real: fetch expired ATM option history from Dhan ("Rolling & Expired Options Data", by moneyness ATM/ATM±1, ~30-day window per call — exact endpoint per https://dhanhq.co/docs/v2/). If unavailable: fail loudly, fall back to synth with a loud warning.
MILESTONE 5 — Ledger + report
Every candidate signal (taken OR skipped) gets one row: date, time, index, contract, side, entry, lot, exit, exit_reason (T1/T2/SL/EOD), pnl, sm5, sm30, rng, C1..C8, verdict, skip_reason, mode. Save to CSV. Print a per-day summary table + totals.
Run the calendar range 2025-10-05 → 2025-10-17; silently keep only actual trading days (5 Oct 2025 was a Sunday — the research doc's date list is internally inconsistent, which is why its day count doesn't match its P&L rows; the user will match outputs to real records later).
Sanity target (scope-limited): the +₹13,452 (gate) / −₹788 (engine raw) targets apply ONLY to the research doc's trading days: Oct 6, 7, 14, 16 (config: sanity.days). Compare the gate total over exactly those four days against +₹13,452, 1-lot sizing, ±₹250. The full calendar range (Oct 5–17) also runs, but its total is reported separately as additional evidence — NEVER compared to the target. Report the actual numbers; if far off, investigate fill/slippage assumptions BEFORE touching thresholds — do NOT tune thresholds to fit.
ACCEPTANCE CRITERIA
test_gate.py proves: each of the 8 checks fails individually → SKIP with that check's ID in skip_reason (C1 tested as a pure function); midday signal → SKIP; rng 0.90 → SKIP; 2 consecutive SLs → 60-min timeout enforced; C5 edges: 12:00:00 → SKIP, 13:00:00 → allowed; C7 edges: day_realised_pnl = −₹7,000 → SKIP (C7 in skip_reason), −₹6,999 → pass.
exits tests prove: a bar spanning both SL and T1 → SL fills first; same for SL and T2.
Black-Scholes sanity: ATM ≈ 0.5 delta; premium decreases as T→0 with spot flat (theta visible).
Full run (Oct 5–17 range) completes from cache in <10 s.
Ledger CSV column names match: date, time, index, contract, side, entry, lot, exit, exit_reason, pnl, sm5, sm30, rng, C1, C2, C3, C4, C5, C6, C7, C8, verdict, skip_reason, mode.
Security: no token in code; .env gitignored; /orders URLs unreachable; 401 prints the exact expiry message.
