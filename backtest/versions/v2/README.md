# Strategy v2 — research branch

v1 (frozen) replayed the specified eight-check gate with an SL/T1/T2 bracket and could not reproduce the research P&L.
v2 asks a different question first: *does a 5-min burst have a forward edge at all, over ~5 years, and does it survive option costs?*

- Read `results/V2_summary.md` for method, findings and caveats. Verdict: **no robustly profitable strategy; one small, decaying, execution-sensitive NIFTY candidate.**
- Code: `../../research/edge_study.py` (index-level edge, train/test), `../../research/option_study.py` (costed option P&L).
- Candidate rule (NIFTY): burst |m5| ≥ 3·σ5 (σ5 = prior-5-session std of 5-min changes); 60-min trend agrees with the burst; bar start not in 12:00–13:00; buy ATM CE (up-burst) / PE (down-burst) at the bar close; exit after 15 minutes; 15% premium stop; no entries before 10:15.
- `config.yaml` here is still a copy of v1's (for `backtest.py`); the candidate's parameters live in the research scripts and are NOT yet wired into the runner.
- Data: `data/cache/` now holds 2022-01-03 → 2026-11-13 for NIFTY and SENSEX (fetched via `CandleStore.fetch_range`, validated identical to per-day fetches).
