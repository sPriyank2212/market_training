# Signals reverse-engineering — session summary (2026-11-16)

**Goal:** work out how the AlphaEdge "Signals" engine generates its NIFTY / SENSEX option signals, using the
screenshots of its feed as ground truth and Dhan market data as the replay source.

---

## 1. What we did today

### 1.1 Screenshots → Excel
- Received 190 phone/tablet screenshots of the Signals feed (`SignalsFeed*.png`, 1640×2360).
- Wrote [`extract_signals.py`](extract_signals.py): local OCR (RapidOCR / ONNX, no cloud calls) with a layout-aware
  parser that reads each trade card.
- Output: [`signals/signals.xlsx`](signals/signals.xlsx) — **306 trades** (219 NIFTY, 87 SENSEX), 2026-10-19 → 2026-11-13.
- Columns: Index, Trade, Date, Time, Entry Premium, Exit Premium, Target 1, Target 2, Premium SL, Side, Expiry, Lot,
  P&L (₹), P&L (%), Status, Source, Notes.

**Bugs found by testing against the real screenshots, and fixed**

| Problem | Cause | Fix |
|---|---|---|
| "Not Triggered" trades got entry 1 / exit 2 | Parser read the digits in the "TARGET 1 / TARGET 2" label row | Values are taken only from rows that contain no words |
| Target 1 overwritten with the date's "13" | "Target 1 Hit" badge treated as a label row | Parse stops at the date/time line; each label row read once |
| P&L 7780 instead of 780 | OCR read ₹ as the digit 7 | Check P&L = (exit − entry) × lot; correct and note it |
| Entry / exit / P&L blank on one card | Stray text from the app beside the browser (split-screen) created a junk row | Skip 1–2 letter junk rows, stop at the next label row |
| Statuses missing / "SLHit" | New statuses (EOD Close, Active, Yet to Activate), lost spaces | Added and normalised |
| Duplicates from overlapping scrolls; half-visible cards | Same trade in several screenshots | De-dupe on index + strike + expiry + minute; drop cut-off cards when a full copy exists |

**Verification:** 0 duplicates; 0 consistency failures (P&L, %, SL < T1 ≤ T2, exit equals the hit level);
all 265 closed trades have entry, exit and P&L; 11 rows compared by eye against the screenshots matched exactly.

### 1.2 What the 306 signals already tell us about the engine

| Observation | Result | Implication |
|---|---|---|
| Signal minute (mod 5) | 70 / 59 / 57 / 60 / 59 | **Not** triggered on 5-min candle closes; faster scan (≈1-min) |
| 12:00–13:00 | 39 signals | No midday blackout in the engine |
| Entry premium, NIFTY | ₹11 – ₹228; 157/191 inside the spec's 120–215 band | No premium band in the engine |
| CE / PE | 203 / 102 | Call-heavy in this up-trending sample |
| Days to expiry | 38 % of signals on expiry day | Many entries are in near-worthless 0-DTE options |
| SL / T1 / T2 vs entry | Median −17 % / +9 % / +23 %; 98 % are multiples of ₹5 | Not fixed percentages; look like spot-derived levels rounded to a ₹5 grid |
| Exits | 188/188 T1 exits and 71/71 SL exits equal the level exactly | Idealised paper fills — no slippage |
| Outcomes (265 executed) | Win 72.5 %, avg win ₹820, avg loss −₹1,585, total +₹41,746 | Edge depends on the high win rate (break-even ≈ 66 %) |
| Profitable days | 9 of 11 | Negative on 3 Nov and 13 Nov |
| Signal spacing (same index/day) | Median 12 min; 23 of 284 within 1 min | Clusters exist |

These are the engine's **raw, unfiltered** signals — the thing the spec's "eight-check gate" was meant to filter.

### 1.3 Existing `backtest/` work reviewed
Read-only Dhan backtester (v1 frozen, v2 research). Headline: the spec's gate result did not reproduce, and the only
evidence-backed edge found was small and short-lived. Details in `backtest/SUMMARY_ALL_TESTS.md`.

---

## 2. Known gaps in the Excel
- **NIFTY 23750 PE (3 Nov)** — only half visible at the bottom of one screenshot and never shown fully elsewhere.
  Present as a row with no date/entry; needs one more screenshot.
- **Live trades whose card header was scrolled off** (e.g. top card of screenshot #2) have no strike line and are not
  extracted. Their closed versions may appear in other screenshots.
- 36 "Not Triggered" rows have blank entry/exit/P&L by design — filter on Status if only executed trades are wanted.
- Only 11 of 306 rows were compared by eye; the rest rely on the automated consistency checks above.

---

## 3. Plan — reverse-engineer the trigger with Dhan data

**Prerequisite:** a fresh Dhan access token and the full client ID in `backtest/.env` (tokens last 24 h).

| # | Test | Data | Question |
|---|---|---|---|
| H1 | Trigger | 1-min spot candles | Spot move over the previous 1/3/5/10 min in the signal's direction vs. random minutes — fit a threshold per index |
| H2 | Strike choice | Spot at signal time | ATM, or ITM/OTM by how many steps? |
| H3 | Entry price / clock | 1-min option candles | Does the real option price at that minute equal the entry premium? Any timestamp offset? |
| H4 | SL / T1 / T2 | Spot + option ranges | Do the levels track spot ATR, option range, or something else? |
| H5 | Outcomes | 1-min option highs/lows | Replay each trade; how often does first-touch reproduce the recorded status (incl. "Not Triggered")? |

**Success criterion (set before looking):** a rule that, on these 11 days, reproduces the signal times with high
recall and few extra firings, and reproduces statuses for most trades. Treat 11 days as a hypothesis-forming sample;
validate any rule on days not used to build it.

---

## 4. Security / housekeeping — action needed
1. **`live_api.txt` is tracked and already pushed** to the GitHub remote. It holds an access token (expired
   2026-11-16 02:02) and embeds the client ID. Remove it from the repo and rotate the credential.
2. **`backtest/.env.example`** has a local, uncommitted edit containing credentials. Do not commit it; restore the blank
   template and put real values only in `backtest/.env`.
3. **`backtest/.gitignore` has a local edit that removed the `.env` line.** Restore it, otherwise `backtest/.env` would be
   committed. (The new root `.gitignore` also ignores `.env` as a safety net.)
4. The access token expires every 24 h; the client ID pasted into `.env.example` is shorter than the ID inside the token,
   so it was probably truncated.

---

## 5. How to run the extractor
```
python -m venv .venv
.venv\Scripts\pip install -r requirements-signals.txt
.venv\Scripts\python extract_signals.py "path\to\screenshots"        # writes signals.xlsx in that folder
.venv\Scripts\python extract_signals.py shots -o trades.csv           # CSV instead
.venv\Scripts\python extract_signals.py shots --indices ALL           # keep every index
.venv\Scripts\python extract_signals.py shots --dump-ocr              # show raw OCR text for debugging
```

## 6. Files added in this change
- `extract_signals.py`, `requirements-signals.txt` — the extractor
- `signals/signals.xlsx` — extracted trades
- `SIGNALS_PROJECT_SUMMARY.md` — this document
- `.gitignore` — ignores `.venv/`, caches, `.env`, and the raw screenshot folder/zip (≈190 MB, show browser tabs)






















DHAN_ACCESS_TOKEN=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJ1c2VyUmVnaW9uIjoiUjEiLCJpc3MiOiJkaGFuIiwicGFydG5lcklkIjoiIiwiZXhwIjoxNzk1MDMzMTAwLCJpYXQiOjE3OTQ5NDY3MDAsInRva2VuQ29uc3VtZXJUeXBlIjoiU0VMRiIsIndlYmhvb2tVcmwiOiIiLCJkaGFuQ2xpZW50SWQiOiIxMTE0NTM1NDQ4In0.IrXjbAPJIgnsCbEh6juHAefe_Nu1lDbC6kOJ8Iv7NVzk2RdNqtPWKOaKZUzjmC2rlv9K6vSn3K8NqOoeU2BfMQ