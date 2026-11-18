# v3 — M0 / M1 summary (2026 re-run)

## M0 scaffold
v3 folder, config (2026 dates, Yahoo anchors, known expiries, warmup.nan_policy=fail), validate.py skeleton, v1 invalidation banners. 68 tests pass under v1 and v3.

## M1 Dhan connection (live call, 2026-11-18)
- securityIds resolved from the instrument master (not hardcoded): NIFTY 13, SENSEX 51.
- NIFTY 2026-10-06: 75 bars, first 09:15 IST, last 15:25 IST, all in 2026. O 22603.25  H 22776.10  L 22561.60  C 22776.10.
- SENSEX 2026-10-06: 75 bars, 09:15 … 15:25. O 72508.05  H 73067.81  L 72384.83  C 73067.81.
- Saturday 2026-10-10 and the Dussehra holiday 2026-10-20: Dhan returns no data -> detected and skipped silently.
- Early look at the Yahoo anchors (full check is M1.5): NIFTY 06-Oct matches within 0.001%. SENSEX 06-Oct high differs: Dhan 73067.81 vs anchor 73281.85 (0.29%, above the 0.15% tolerance); open, low and close match.
