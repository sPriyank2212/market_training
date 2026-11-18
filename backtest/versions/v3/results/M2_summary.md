# v3 — M2 candle cache + feature engine (2026 data)

- 20 day-index series (10 trading days x NIFTY/SENSEX, 5–16 Oct 2026), all 75 bars, 09:15 → 15:25, max gap 5 min, no missing bars. Validation gate passed first (M1.5).
- Features (per bar, no look-ahead): m5, m30, rng (running day high/low, 0.5 guard), trend (sign of 60-min change), day open/high/low, ts_close/sig_time.
- Warm-up (within-day lookbacks): m5 NaN on bar 1; m30 NaN until 09:45 (6 bars); trend NaN until 10:15 (12 bars). `warmup.nan_policy: fail` → a check needing a NaN FAILS.
- Burst candidates (|m5| >= th_trig; no gate yet): **289**, of which **76 (26 %) fall in the warm-up window** — higher than the 21 % quoted in the prompt, because the 2026 days have more early-morning bursts.
- No look-ahead verified: features on truncated data equal full-day values (6 days x 3 cut points); 5 feature tests pass.
- Cache: 20 CSVs in data/cache for the window. Re-run from cache: 0 network calls, 0.33 s.
- File: `M2_data_quality.csv`.
