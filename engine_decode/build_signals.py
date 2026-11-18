"""signals/signals.xlsx (OCR-decoded engine cards) -> engine_decode/data/signals_clean.csv (one row per card with date+time)."""
import re, pandas as pd
from pathlib import Path
R = Path(__file__).resolve().parent
d = pd.read_excel(R.parent / "signals" / "signals.xlsx")
d = d.dropna(subset=["Date", "Time"]).copy()
m = d.Trade.str.extract(r"(\d+)\s*(CE|PE)")
d["strike"] = m[0].astype(int); d["opt"] = m[1]
d["ts"] = pd.to_datetime(d.Date + " " + d.Time).dt.tz_localize("Asia/Kolkata")
d["date"] = d.ts.dt.date; d["time"] = d.Time
d = d.rename(columns={"Index": "index", "Entry Premium": "entry", "Exit Premium": "exit", "Target 1": "t1", "Target 2": "t2",
                      "Premium SL": "sl", "P&L (Rs)": "pnl", "P&L (%)": "pnl_pct", "Status": "status", "Lot": "lot", "Expiry": "expiry"})
d = d[["ts", "date", "time", "index", "strike", "opt", "expiry", "lot", "entry", "sl", "t1", "t2", "exit", "pnl", "pnl_pct", "status"]]
d = d.sort_values(["ts", "index"]).reset_index(drop=True)
d.to_csv(R / "data" / "signals_clean.csv", index=False)
print(len(d), "cards;", d.ts.dt.date.nunique(), "days")
print(d.groupby("date").size().to_string())
