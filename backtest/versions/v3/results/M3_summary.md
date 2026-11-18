# v3 — M3 eight-check gate (2026 data)

Gate logic is the reviewed v1 logic (unchanged); spec rulings applied: C5 blocked iff 12:00 <= t < 13:00; C7 passes iff pnl > -7000; C6 timeout starts at the 2nd consecutive SL's exit and is blocked at +59:59, allowed at +60:00; NaN in a needed value FAILS that check (`warmup.nan_policy: fail`); C8 = NA (visible pass) when no premium; flip rule disabled; MAXTRADES is a separate guard. All eight checks are evaluated with no short-circuit.

## Acceptance
- test_gate.py: 27 tests pass (one failed check -> SKIP with exactly its ID; midday + 12:00:00/13:00:00 edges; rng 0.90; 2 SL -> 60-min timeout; day brake -7000 SKIP / -6999 pass; NaN fails; per-index thresholds; PE signs; flip on/off; daily cap). Gate tests now use 2026 dates.
- **Mutation self-check** (`tests/test_mutation.py`): 6 deliberate off-by-one bugs (C7 `>=`, C5 end-inclusive, C5 start-exclusive, C2 `<=`, C4 inclusive, 59-min timeout) injected into a copy of gate.py — **all 6 killed**; unmutated copy passes.
- Full suite: 85 tests pass.

## Preview on the 2026 candidates (own-scanner mode; no exits simulated yet, so C6/C7 inactive; C8 = NA — premium arrives in M4)
- 289 burst candidates -> **18 TAKE / 271 SKIP** (NIFTY 8/136, SENSEX 10/153).
- Failures per check: C1 0 (tautology, as acknowledged) | C2 145 | C3 139 | C4 176 | C5 33 | C6 0 | C7 0 | C8 NA x289. **Most-failed: C4 (range position).**
- SKIPs caused by exactly one check: C3 42, C4 42, C2 13, C5 13.
- All 76 candidates before 10:15 (trend NaN) are SKIP; none TAKE.
- File: `M3_gate_preview.csv`.
