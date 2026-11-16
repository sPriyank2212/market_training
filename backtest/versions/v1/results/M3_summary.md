# M3 — Eight-check gate  ✅ (code + tests); preview run is PRE-P&L

## Delivered
- `gate.py`: `c1..c8` pure functions; `evaluate()` applies all eight with no short-circuit (ledger shows every result); `DayState` (consecutive SL, timeout, realised P&L, trades taken, flip state); `generate_candidates()` (own-scanner); flip rule implemented but **disabled** (`flip_rule.enabled: false`).
- Boundaries as ruled: C4 strict both sides; **C5 blocked iff 12:00 <= t < 13:00**; **C7 passes iff pnl > −7000 (−7000 SKIPs)**; C8 band inclusive, no premium → `NA` (pass, visible).
- Implementation choices to know about:
  - NaN needed by a check → that check **FAILS** (warm-up bars never pass silently).
  - On the 2nd consecutive SL the 60-min timeout starts at that exit time and the chain counter resets; timeout ends exactly at +60:00 (allowed at 60:00, blocked at 59:59).
  - `risk.max_trades_per_day` is enforced as an extra guard reported as `MAXTRADES` (not one of the eight).
  - Only a full stop-out counts toward the SL chain (`register_exit(is_sl=...)`); a T1-then-cost exit is not an SL. Confirm at M4.

## Tests: 44 passed, 2 skipped (M4 placeholders)
Each check fails individually with exactly its ID in `skip_reason`; midday; rng 0.90; 2×SL → 60-min timeout; C5 12:00:00/13:00:00; C7 −7000/−6999; C1 pure; PE sign handling; per-index thresholds; NaN policy; flip on/off; daily cap; scanner.
**Mutation check:** 6 deliberate off-by-one bugs (C7 `>=`, C5 end-inclusive, C5 start-exclusive, C2 `<=`, C4 inclusive, 59-min timeout) were each caught by the suite.

## Preview run (20 index-days; fresh state per day; no exits yet)
`M3_gate_preview.csv` — 201 candidates → **32 TAKE / 169 SKIP**.
C6, C7, C8 never fire here by construction (no P&L or premium until M4), and C1 never fires (tautology in own-scanner mode, as ruled).

| Check | NIFTY fails | SENSEX fails |
|---|---|---|
| C2 | 32 | 53 |
| C3 | 33 | 56 |
| C4 | 35 | 46 |
| C5 | 11 | 15 |

Sole-veto signals: C3 44, C2 18, C4 15, C5 7.

## ⚠ Decision needed before M4: opening-hour warm-up
Lookbacks are within-day, so `m30` is NaN before 09:45 and `trend` before 10:15. **43 of 201 candidates (21%) fall in that window** (31 also lack m30). Under the NaN=fail policy, 43 of the 89 C3 fails and 31 of the 85 C2 fails are purely warm-up. Ignoring NaNs would lift TAKEs from 32 to ~57 — so this choice materially changes results.

Options: (a) keep NaN=fail (conservative, trades only after 10:15); (b) seed lookbacks from the prior session's closes (continuous series, like a live engine); (c) treat NaN as pass. This must be settled **before** P&L is seen, so it is a data-definition choice and not tuning to the +₹13,452 target.
