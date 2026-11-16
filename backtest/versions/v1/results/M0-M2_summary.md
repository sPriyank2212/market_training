# Backtester — results for M0, M1, M2

Generated 2026-11-15. Spec: `../kimi-code-backtest-prompt.md` (patched with the four rulings: sanity scope, SL-first tie-break, C7 strict `>`, C5 `12:00 <= t < 13:00`).

## M0 — Scaffold  ✅
- Files per spec tree, plus `.gitignore`, `data/cache/`, extra test files (exits, premium, security).
- `dhan_client.py` is complete: `/orders` guard + allow-list (`/charts/` only) run **before** any network call; token masked; 401/403 prints the exact expiry message; retries with backoff.
- `tests/test_security.py`: 12 tests pass (orders variants blocked, non-allow-listed paths blocked, no network on blocked URL, token masked, exact 401 text).
- Environment: Python 3.14.0 (spec assumed 3.12). `requests` prints a harmless urllib3/chardet version warning.
- Old token in `live_api.txt` was never read by the tool; user rotated it.

## M1 — Dhan connection  ✅
| Check | Result |
|---|---|
| NIFTY 2025-10-06 | 75 bars, 09:15 → 15:25 IST |
| NIFTY securityId | 13 (from instrument master, 225,137 rows, cached) |
| SENSEX securityId | 51; 75 bars on 2025-10-06 |
| Sunday 2025-10-05 | skipped, no call |
| Holiday 2025-10-02 | Dhan returned no data; handled |

Spec changes found while verifying against Dhan docs / live:
1. `fromDate`/`toDate` take `YYYY-MM-DD HH:MM:SS` (not date-only).
2. `fromDate` is **exclusive** at the boundary — requesting 09:15:00 drops the 09:15 bar (74 bars). Now request from `data.fetch_from` = 09:00 and filter to session.
3. Timestamps are true UTC epoch seconds → IST gives bar-start stamps (09:15 first).
4. Yahoo fallback **not needed** — Dhan serves Oct 2025 history. (Yahoo's 5-min lookback is ~60 days, so it could not have served these dates anyway.)

## M2 — Cache + features  ✅
- 10 trading days (Oct 6–10, 13–17) × 2 indices, all from Dhan, 75 bars each, zero gaps. Detail: `M2_data_quality.csv`.
- Cold fill ≈ 12 s per index (10 calls); warm re-run = 0 network calls, ≈ 2.7 s wall (mostly pandas import).
- Cache layers: `cache → Dhan → data/manual/{SYMBOL}_{date}.csv`. Dhan-confirmed holidays get a `.nodata` marker; *failed* requests are never cached as holidays.
- Features: `m5, m30, rng, trend, day_open/high/low`, plus `ts_close` and `sig_time`. No look-ahead (tested). Lookbacks are within-day only → `m30` NaN for first 6 bars (<09:45), `trend` NaN for first 12 (<10:15).
- Pre-gate candidate counts (|m5| ≥ trigger): NIFTY 4–12/day, SENSEX 5–19/day.
- Tests: 17 passed, 3 skipped (placeholders).

## Open decisions carried forward
| # | Decision | Default in use |
|---|---|---|
| 1 | Signal stamp basis | `bar_start` (`features.signal_time`); `bar_close` available |
| 2 | NaN warm-up values | A NaN needed by a check **fails** that check (logged, not silently passed) |
