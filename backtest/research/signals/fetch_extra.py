"""Extra read-only context series for the signals study: India VIX (index) and Nov-2026 NIFTY / SENSEX futures
(1-min OHLCV + OI), for every trading day in the signals range. Cached under data/cache/signals/ (git-ignored)."""
import time
from fetch_data import range_days, SLEEP
from common import *
SERIES = {"VIX": dict(sec=21, seg="IDX_I", inst="INDEX"),
          "NIFTYFUT": dict(sec=61471, seg="NSE_FNO", inst="FUTIDX"),
          "SENSEXFUT": dict(sec=1100929, seg="BSE_FNO", inst="FUTIDX")}
c = DhanClient(load_config("v1")); n = 0
for day in sorted({d for _, d in range_days()}):
    for name, s in SERIES.items():
        p = CACHE / f"x_{name}_{day}.csv"
        if p.exists(): continue
        body = {"securityId": str(s["sec"]), "exchangeSegment": s["seg"], "instrument": s["inst"], "interval": "1",
                "oi": s["inst"] == "FUTIDX", "fromDate": f"{day} 09:00:00", "toDate": f"{day} 15:30:00"}
        try: r = c.post("/charts/intraday", body)
        except TokenExpiredError: raise SystemExit("token expired - refresh backtest/.env")
        except Exception as e: print(name, day, "ERR", str(e)[:120]); continue
        time.sleep(SLEEP); n += 1
        ts = r.get("timestamp") or []
        cols = ["open", "high", "low", "close", "volume"] + (["open_interest"] if "open_interest" in r else [])
        df = pd.DataFrame({k: r[k] for k in cols}) if ts else pd.DataFrame(columns=cols)
        df.insert(0, "ts", pd.DatetimeIndex(pd.to_datetime(ts, unit="s", utc=True)).tz_convert(IST).strftime("%Y-%m-%d %H:%M:%S") if ts else [])
        df.to_csv(p, index=False)
print("extra done", n, "calls")
