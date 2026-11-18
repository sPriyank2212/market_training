# Strategy v3 — v1 logic, re-run on the correct year (2026)

**Why:** v1 fetched 2025-10-05…17 candles. The engine signals, screenshots and the +₹13,452 target are from **October 2026** (NIFTY 27 Oct 2026 matches the research tape; Oct 2025 NIFTY traded ~2,000 points higher). v1's "target not reproduced" conclusion is therefore **invalid** — it compared two different years.

**What changes vs v1:** dates (sample days 2026-10-05, 06, 07, 14, 16; window 2026-10-05…17), expiry handling (resolve from instrument master / trading calendar, assert against known dates — no hardcoded weekday), a mandatory **data-validation gate** (`validate.py`, M1.5: year assert, Yahoo anchor check, bar-count check), `warmup.nan_policy` as an explicit config key (default `fail`).
**What does not change:** the eight-check gate, thresholds, exits, tie-breaks, synthetic premium model — identical to the reviewed, tested v1 logic.

- `spec.md` — frozen copy of the 2026 prompt (`kimi-code-backtest-prompt-2026.md`)
- `config.yaml` — every threshold, validation anchors, known expiries
- `results/` — milestone summaries and ledgers (written as milestones complete)

**Reading the output:** this run is *own-scanner* mode with synthetic premiums. It is not expected to land on +₹13,452 and must not be tuned toward it. The engine-gate A/B needs the decoded 101-signal list (not supplied yet).
