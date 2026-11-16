# M4 — Premium model + exits  ✅ (v1, mode: synth)

## Delivered
- `premium.py`: Black-Scholes (r 6.5%, IV 13%, no dividends). Contract fixed at entry from the entry-bar spot (ATM, `itm_steps` configurable). Weekly expiry weekday per index (NIFTY Tue, SENSEX Thu), expiry 15:30 IST, `min_T_minutes` floor guards expiry-day T→0. Theta emerges from T shrinking bar by bar — no separate theta term. Per-bar premium high/low derived from the bar's spot high/low (monotone for fixed strike/T).
- `exits.py`: SL −15% (never widened), T1 +8%, T2 +25%, flat 15:15. **Ties: SL fills first** (SL vs T1, SL vs T2, cost-stop vs T2). Fills at the level, no slippage.
- REAL mode: `get_path()` tries real, and on failure prints a loud WARNING and falls back to synth (tested). Real fetch itself is **not yet implemented** — see findings.

## Tests: 65 passed
BS: ATM delta, put-call parity, theta visible (premium falls as T→0, flat spot, CE and PE), expiry-day floor, expiry-date rule, strike/ITM selection, PE/CE bar-range ordering, real→synth fallback warning.
Exits: plain SL; bar spanning SL+T1 → SL; SL+T2 → SL; T1→T2; T1→cost; cost-vs-T2 tie → cost; gap through T1+T2; stop never reverts to original SL; EOD at 15:15 ignores later bars; EOD after T1 sells only remainder.
Note: ATM call delta is 0.531, not 0.500, because r = 6.5% puts the forward above spot; delta at the forward strike is ≈0.5 (asserted).

## Assumptions made where the spec was silent (v1)
| Gap | v1 choice |
|---|---|
| Share sold at T1 | `exits.t1_fraction: 0.5` |
| Cost-stop in the bar that fills T1 | not tested until next bar |
| What counts as "SL" for C6 | only exit_reason `SL` (full stop, no T1) |
| Entry fill | signal-bar close premium, no slippage/tick rounding/brokerage |
| Flatten | close of last bar completing by 15:15; no entries whose bar closes ≥ 15:15 |

## Findings (read these before M5)
### 1. C8 acts as a days-to-expiry filter on ATM nearest-weekly premiums
`M4_c8_premium_check.csv`: of 201 candidates, 89 pass C8 (NIFTY 46/81, SENSEX 43/120).
- NIFTY passes only Wed–Fri (4–6 DTE, premium ≈ 120–200); **Mon (≈1 DTE, premium ≈ 60–85) and Tue/expiry day (≈ 10–40) never pass.**
- SENSEX passes Mon/Tue (2–3 DTE) and fails Wed/Thu (≈0–1 DTE) and Fri (6 DTE, premium ≈ 500–630 > 460, i.e. *above* the band).
- On the four sanity days exactly one index is in-band each day: Oct 6 SENSEX, Oct 7 SENSEX, Oct 14 SENSEX, Oct 16 NIFTY. Plausibly why the research doc's days look as they do.

### 2. Real option data is available and reachable (probe, NIFTY 2025-10-06)
- `POST /charts/rollingoption` works with `expiryCode: 1` (**`0` is rejected** with DH-905 despite the docs), date-only `fromDate/toDate`, `interval "5"`. A one-day request returned 150 rows (Oct 6 **and** Oct 7), i.e. `toDate` behaved inclusively.
- Rolling-ATM series carries `strike, spot, iv, open/high/low/close`; the strike rolls with spot (5 different strikes on Oct 6), so a fixed-strike position needs a multi-strike fetch (ATM±k) — not built yet.
- Real ATM call on Oct 6 (≈1 DTE): premium 44–87, IV 6–12% (≈8.7% typical). BS at IV 13% overstates it by ≈20% (median real/BS = 0.83). Real premium is below the NIFTY band on that day, same as synth.

### 3. Lot size cannot be verified for Oct 2025
Instrument master reflects today's lots (NIFTY 65; SENSEX 20/25). My recollection is NIFTY's lot was 75 in Oct 2025 — unverified. P&L is linear in lot size (75/65 = +15%), which is large relative to the ±₹250 tolerance. v1 keeps the spec's 65/20.

## Not tuned
No thresholds, IV or bands were changed in response to these findings (v1 stays as specified). All are v2 candidates: calibrated/lower IV, contract selection (next expiry or ITM so premium sits in the band), real-premium mode, lot-size correction.
