import pandas as pd, numpy as np
from pathlib import Path
R = Path(__file__).resolve().parent
IST = "Asia/Kolkata"

def load_sigs():
    s = pd.read_csv(R / "data" / "signals_clean.csv"); s["ts"] = pd.to_datetime(s.ts, utc=True).dt.tz_convert(IST); return s

_c = {}
def load_c(sym, day):
    k = (sym, str(day))
    if k not in _c:
        df = pd.read_csv(R / "data" / "c1m" / f"{sym}_{day}.csv"); df["ts"] = pd.to_datetime(df.ts, utc=True).dt.tz_convert(IST)
        _c[k] = df.set_index("ts")
    return _c[k]

def days():
    return sorted(load_sigs().date.unique())
