"""Fetch 1-min NIFTY/SENSEX index candles (READ-ONLY Dhan /charts/intraday) for 2026-10-19 .. 2026-11-13.
Reuses backtest/dhan_client.py (token only from backtest/.env, /orders blocked, path allow-list).
Caches one CSV per symbol/day in engine_decode/data/c1m/. Re-runs make no network calls for cached days."""
import sys
from datetime import date, timedelta
from pathlib import Path
import pandas as pd

BT = Path(__file__).resolve().parent.parent / "backtest"
sys.path.insert(0, str(BT))
from dhan_client import DhanClient, TokenExpiredError, load_config   # noqa: E402
from candles import load_scrip_master, resolve_index_id, IST          # noqa: E402

OUT = Path(__file__).resolve().parent / "data" / "c1m"
OUT.mkdir(parents=True, exist_ok=True)


def main(start=date(2026, 10, 19), end=date(2026, 11, 13)):
    cfg = load_config("v3")
    cl = DhanClient(cfg)
    master = load_scrip_master(cfg)
    for sym in ("NIFTY", "SENSEX"):
        sid = resolve_index_id(master, sym)
        d = start
        while d <= end:
            f, nd = OUT / f"{sym}_{d}.csv", OUT / f"{sym}_{d}.nodata"
            if d.weekday() < 5 and not f.exists() and not nd.exists():
                body = {"securityId": sid, "exchangeSegment": "IDX_I", "instrument": "INDEX", "interval": "1",
                        "oi": False, "fromDate": f"{d} 09:00:00", "toDate": f"{d} 15:35:00"}
                try:
                    r = cl.post("/charts/intraday", body)
                except TokenExpiredError:
                    print("TOKEN EXPIRED"); return 2
                ts = r.get("timestamp") or []
                if not ts:
                    nd.write_text("no data\n"); print(sym, d, "no data")
                else:
                    df = pd.DataFrame({k: r[k] for k in ("open", "high", "low", "close", "volume")})
                    df["ts"] = pd.to_datetime(ts, unit="s", utc=True).dt.tz_convert(IST) if hasattr(pd.to_datetime(ts, unit="s", utc=True), "dt") else pd.to_datetime(ts, unit="s", utc=True).tz_convert(IST)
                    df = df[["ts", "open", "high", "low", "close", "volume"]]
                    df.to_csv(f, index=False); print(sym, d, len(df), df.ts.iloc[0].strftime("%H:%M"), df.ts.iloc[-1].strftime("%H:%M"), "vol", int(df.volume.sum()))
            d += timedelta(days=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
