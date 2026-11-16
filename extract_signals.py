"""
Extract trade data from AlphaEdge-style "Signals" app screenshots into CSV / Excel.

For every trade card found it pulls:
    Index (NIFTY / SENSEX), Trade (e.g. "25100 PE"), Date, Time,
    Entry Premium, Exit Premium
plus a few extras (Side, Expiry, Lot, SL, Target 1/2, P&L, Status, Source).

Usage:
    python extract_signals.py shots/                      -> shots/signals.xlsx
    python extract_signals.py a.png b.png -o trades.csv   -> CSV
    python extract_signals.py shots/ --indices NIFTY SENSEX BANKNIFTY
    python extract_signals.py shots/ --dump-ocr           -> print raw OCR text (debugging)

Setup:
    pip install -r requirements-signals.txt
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
KNOWN_INDICES = {"NIFTY", "SENSEX", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "BANKEX"}
REF_WIDTH = 1390  # width of the reference screenshot; vertical distances scale from it

MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], 1)}

# "25,100 PE · 17 Nov 2026"  (the "·" is often misread, so the separator is loose)
STRIKE_RE = re.compile(r"(\d{1,3},?\d{3})\s*(CE|PE)\W{0,3}\s*(\d{1,2})\s*([A-Za-z]{3})[A-Za-z]*\s*(\d{4})", re.I)
# "13 Nov at 09:18 AM"
WHEN_RE = re.compile(r"(\d{1,2})\s*([A-Za-z]{3})[A-Za-z]*\s*at\s*(\d{1,2})\s*[:.]\s*(\d{2})\s*([AP])\.?\s*M", re.I)
# "+₹815.75 (+7.73%)"
PNL_RE = re.compile(r"([+\-−])?\s*\D{0,2}?\s*(\d[\d,]*(?:\.\d+)?)\s*\(\s*([+\-−])?\s*(\d+(?:\.\d+)?)\s*%\s*\)")
PRICE_RE = re.compile(r"\d[\d,]*\.\d{1,2}|\d[\d,]*")
LOT_RE = re.compile(r"Lot\s*[:.]?\s*(\d+)", re.I)
STATUS_RE = re.compile(
    r"(Target\s*[1-9I]?\s*Hit|(?:SL|Stop\s*Loss)\s*Hit|Not\s*Triggered|Yet\s*to\s*Activate|EOD\s*Close|Active|Expired|Exited|Closed|Open|Live)", re.I)


def _clean_status(s: str) -> str:
    s = re.sub(r"(?i)target\s*([1-9I]?)\s*hit", lambda m: "Target " + (m.group(1).replace("I", "1") + " " if m.group(1) else "") + "Hit", s)
    s = re.sub(r"(?i)^(sl|stop\s*loss)\s*hit$", "SL Hit", s.strip())
    s = re.sub(r"(?i)^not\s*triggered$", "Not Triggered", s)
    return re.sub(r"\s+", " ", s).strip()


@dataclass
class Item:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


# --------------------------------------------------------------------------- OCR

_engine = None


def run_ocr(path: Path) -> list[Item]:
    """Run RapidOCR on one image and return positioned text items."""
    global _engine
    if _engine is None:
        try:
            from rapidocr import RapidOCR  # rapidocr >= 2
        except ImportError:
            from rapidocr_onnxruntime import RapidOCR  # older package name
        _engine = RapidOCR()

    res = _engine(str(path))
    if hasattr(res, "txts"):  # rapidocr >= 2 result object
        boxes = res.boxes if res.boxes is not None else []
        txts = res.txts if res.txts is not None else []
    else:  # (list of [box, text, score], elapsed)
        data = res[0] or []
        boxes = [d[0] for d in data]
        txts = [d[1] for d in data]

    items = []
    for box, txt in zip(boxes, txts):
        xs = [p[0] for p in box]
        ys = [p[1] for p in box]
        items.append(Item(str(txt), min(xs), min(ys), max(xs), max(ys)))
    return items


def image_width(path: Path) -> int:
    from PIL import Image

    with Image.open(path) as im:
        return im.size[0]


# ------------------------------------------------------------------------ parsing

def _num(s: str) -> float:
    return float(s.replace(",", ""))


def _prices(text: str) -> list[float]:
    return [_num(m) for m in PRICE_RE.findall(text)]


def _rows(items: list[Item], tol: float) -> list[list[Item]]:
    """Group items into visual rows (same baseline), each row sorted left-to-right."""
    rows: list[list[Item]] = []
    for it in sorted(items, key=lambda i: i.cy):
        if rows and abs(it.cy - sum(r.cy for r in rows[-1]) / len(rows[-1])) <= tol:
            rows[-1].append(it)
        else:
            rows.append([it])
    return [sorted(r, key=lambda i: i.x0) for r in rows]


def _row_text(row: list[Item]) -> str:
    return " ".join(i.text for i in row)


def _guess_index(strike: int) -> str:
    if 10000 <= strike < 35000:
        return "NIFTY"
    if 60000 <= strike < 100000:
        return "SENSEX"
    return "UNKNOWN"


def _resolve_year(day: int, month: int, expiry: date) -> int:
    """Trade date has no year; use the expiry's year, minus one if it would fall after expiry."""
    year = expiry.year
    if date(year, month, min(day, 28)) > expiry:
        year -= 1
    return year


def parse_cards(items: list[Item], width: int, source: str) -> list[dict]:
    s = width / REF_WIDTH
    anchors = []
    for it in sorted(items, key=lambda i: i.cy):
        m = STRIKE_RE.search(it.text)
        if m:
            anchors.append((it, m))
    if not anchors:
        return []

    # a card starts ~100px (reference scale) above its "strike · expiry" line (index name + BUY badge)
    bounds = [a.cy - 100 * s for a, _ in anchors] + [float("inf")]
    out = []
    for n, (anchor, m) in enumerate(anchors):
        region = [i for i in items if bounds[n] <= i.cy < bounds[n + 1]]
        strike = int(m.group(1).replace(",", ""))
        opt_type = m.group(2).upper()
        expiry = date(int(m.group(5)), MONTHS.get(m.group(4).upper(), 1), int(m.group(3)))
        notes = []

        # index name: closest known name above the strike line
        index = None
        for it in sorted((i for i in region if i.cy < anchor.cy), key=lambda i: -i.cy):
            cleaned = re.sub(r"[^A-Z]", "", it.text.upper())
            if cleaned in KNOWN_INDICES:
                index = cleaned
                break
        if index is None:
            index = _guess_index(strike)
            notes.append("index inferred from strike (header not readable)")

        side = ""
        for it in region:
            t = re.sub(r"[^A-Z]", "", it.text.upper())
            if t in ("BUY", "SELL") and it.cy < anchor.cy + 20 * s:
                side = t

        rows = _rows(region, tol=14 * s)
        texts = [_row_text(r) for r in rows]

        entry = exit_ = pnl = pnl_pct = sl = t1 = t2 = None
        seen_a = seen_b = False  # each label row is read once, so a neighbouring card can't overwrite it
        for idx, txt in enumerate(texts):
            up = re.sub(r"[^A-Z0-9]", "", txt.upper())
            if WHEN_RE.search(txt):
                break  # the date/time line is the last line of a card
            # row of labels -> the row directly below holds the values
            # (untriggered trades show "-" there, so don't skip ahead to the next row with digits)
            # Skip junk rows (stray 1-2 letter OCR noise from the app next to the browser in split-screen),
            # but stop at the next label/status row: a price row never contains a word.
            vals = ""
            for k in range(idx + 1, min(idx + 4, len(texts))):
                if re.search(r"[A-Za-z]{3,}", texts[k]):
                    break
                if re.search(r"\d", texts[k]):
                    vals = texts[k]
                    break
            if ("ENTRYPREMIUM" in up or "EXITPREMIUM" in up) and not seen_a:
                seen_a = True
                pm = PNL_RE.search(vals)
                if pm:
                    pnl = _num(pm.group(2))
                    pnl_pct = float(pm.group(4))
                    negative = "-" in (pm.group(1) or "") + (pm.group(3) or "") or "−" in (pm.group(1) or "")
                    if negative:
                        pnl, pnl_pct = -pnl, -pnl_pct
                    vals = vals[:pm.start()] + " " + vals[pm.end():]
                nums = _prices(vals)
                has_entry, has_exit = "ENTRYPREMIUM" in up, "EXITPREMIUM" in up
                if has_entry and nums:
                    entry = nums.pop(0)
                if has_exit and nums:
                    exit_ = nums.pop(0)
            elif ("PREMIUMSL" in up or ("TARGET" in up and "HIT" not in up)) and not seen_b:
                seen_b = True
                labels = re.findall(r"SL|TARGET\s*[1I]|TARGET\s*[2Z]", re.sub(r"PREMIUM", "", txt.upper()))
                nums = _prices(vals)
                for lab, val in zip(labels, nums):
                    if lab.startswith("SL"):
                        sl = val
                    elif lab[-1] in "1I":
                        t1 = val
                    else:
                        t2 = val

        when = lot = status = None
        for txt in texts:
            if when is None and (w := WHEN_RE.search(txt)):
                when = w
            if lot is None and (l := LOT_RE.search(txt)):
                lot = int(l.group(1))
            if status is None and (st := STATUS_RE.search(txt)):
                status = _clean_status(st.group(1))

        trade_date = trade_time = ""
        if when:
            day, mon = int(when.group(1)), MONTHS.get(when.group(2).upper(), 0)
            if mon:
                trade_date = date(_resolve_year(day, mon, expiry), mon, day).isoformat()
            hh, mm, ampm = int(when.group(3)), when.group(4), when.group(5).upper()
            hh = hh % 12 + (12 if ampm == "P" else 0)
            trade_time = f"{hh:02d}:{mm}"
        else:
            notes.append("date/time not found")
        if entry is None and re.sub(r"\s", "", (status or "").lower()) not in ("nottriggered", "yettoactivate"):
            notes.append("entry not found")
        pending = re.sub(r"\s", "", (status or "").lower()) in ("nottriggered", "yettoactivate")
        if (t1 is None or t2 is None) and not pending:
            notes.append("target 1/2 not found")

        # Self-checks: P&L = (exit - entry) * lot. The rupee sign is sometimes misread as a digit ("7").
        if None not in (entry, exit_, lot, pnl, pnl_pct) and entry:
            expected = (exit_ - entry) * lot
            if abs(expected - pnl) > max(1.0, abs(pnl) * 0.005):
                if abs(pnl / (entry * lot) * 100 - pnl_pct) <= 0.3:
                    notes.append("entry/exit don't match P&L - check this row")
                else:
                    notes.append(f"P&L corrected from {pnl:g} (OCR misread)")
                    pnl = round(expected, 2)
        if None not in (sl, t1, t2) and not (sl < t1 <= t2):
            notes.append("SL/targets look inconsistent - check this row")

        out.append({
            "Index": index,
            "Trade": f"{strike} {opt_type}",
            "Date": trade_date,
            "Time": trade_time,
            "Entry Premium": entry,
            "Exit Premium": exit_,
            "Target 1": t1,
            "Target 2": t2,
            "Premium SL": sl,
            "Side": side,
            "Expiry": expiry.isoformat(),
            "Lot": lot,
            "P&L (Rs)": pnl,
            "P&L (%)": pnl_pct,
            "Status": status or "",
            "Source": source,
            "Notes": "; ".join(notes),
        })
    return out


# --------------------------------------------------------------------------- I/O

def collect_images(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for p in map(Path, paths):
        if p.is_dir():
            files += sorted(f for f in p.iterdir() if f.suffix.lower() in IMAGE_EXTS)
        elif p.is_file():
            files.append(p)
        else:
            print(f"warning: {p} not found", file=sys.stderr)
    return files


def dedupe(rows: list[dict]) -> list[dict]:
    """Scrolling screenshots overlap, so the same trade can appear twice."""
    # A card cut off at the bottom of a screenshot has no date/time. Drop it when the same trade
    # appears complete elsewhere (it's fully visible at the top of the next screenshot).
    complete = {(r["Index"], r["Trade"], r["Expiry"]) for r in rows if r["Date"]}
    rows = [r for r in rows if r["Date"] or (r["Index"], r["Trade"], r["Expiry"]) not in complete]

    # Same trade = same index, strike, expiry and minute. If it was read twice (overlapping screenshots),
    # keep the copy with the most fields filled in and the fewest notes.
    def quality(r):
        return (sum(v is not None and v != "" for k, v in r.items() if k != "Notes"), -len(r["Notes"]))

    best: dict = {}
    for r in rows:
        key = (r["Index"], r["Trade"], r["Expiry"], r["Date"], r["Time"]) if r["Date"] else id(r)
        if key not in best or quality(r) > quality(best[key]):
            best[key] = r
    return list(best.values())


def write_output(rows: list[dict], out: Path) -> None:
    if not rows:
        return
    cols = list(rows[0].keys())
    if out.suffix.lower() == ".csv":
        with out.open("w", newline="", encoding="utf-8-sig") as f:  # BOM so Excel opens it cleanly
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
    else:
        from openpyxl import Workbook
        from openpyxl.styles import Font
        from openpyxl.utils import get_column_letter

        wb = Workbook()
        ws = wb.active
        ws.title = "Trades"
        ws.append(cols)
        for r in rows:
            ws.append([r[c] for c in cols])
        for c in ws[1]:
            c.font = Font(bold=True)
        ws.freeze_panes = "A2"
        for i, c in enumerate(cols, 1):
            width = max(len(str(c)), *(len(str(r[c])) for r in rows if r[c] is not None))
            ws.column_dimensions[get_column_letter(i)].width = min(width + 2, 40)
        wb.save(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="*", default=["."],
                    help="screenshot folder(s) and/or files (default: current folder)")
    ap.add_argument("-o", "--output", default=None,
                    help="output .xlsx or .csv (default: signals.xlsx inside the first input folder)")
    ap.add_argument("--indices", nargs="+", default=["NIFTY", "SENSEX"],
                    help="indices to keep (default: NIFTY SENSEX); use ALL for everything")
    ap.add_argument("--dump-ocr", action="store_true", help="print the OCR text lines of each image")
    args = ap.parse_args()

    images = collect_images(args.inputs)
    if not images:
        print("No images found.", file=sys.stderr)
        return 1

    keep = None if "ALL" in {i.upper() for i in args.indices} else {i.upper() for i in args.indices}
    rows: list[dict] = []
    for img in images:
        items = run_ocr(img)
        if args.dump_ocr:
            print(f"--- {img.name}")
            for r in _rows(items, tol=14 * image_width(img) / REF_WIDTH):
                print("  ", _row_text(r))
        found = parse_cards(items, image_width(img), img.name)
        print(f"{img.name}: {len(found)} trade card(s)")
        rows += found

    rows = dedupe(rows)
    if keep is not None:
        rows = [r for r in rows if r["Index"] in keep]
    rows.sort(key=lambda r: (r["Date"], r["Time"]))

    if not rows:
        print("No matching trades found.", file=sys.stderr)
        return 1
    if args.output:
        out = Path(args.output)
    else:
        first = Path(args.inputs[0])
        out = (first if first.is_dir() else first.parent) / "signals.xlsx"
    write_output(rows, out)
    print(f"Wrote {len(rows)} trade(s) to {out}")
    flagged = [r for r in rows if r["Notes"]]
    if flagged:
        print(f"{len(flagged)} row(s) have notes - check the 'Notes' column.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
