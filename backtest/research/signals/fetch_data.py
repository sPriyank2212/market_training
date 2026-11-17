"""Fetch + cache 1-minute spot and rolling-option candles for the signals study. READ-ONLY, idempotent.

Spot   : POST /charts/intraday      -> CACHE/spot_{SYM}_{day}.csv
Options: POST /charts/rollingoption -> CACHE/opt_{SYM}_{day}_c{code}_{CE|PE}_k{k:+d}.csv
         (ATM+k rolling strike, expiryFlag WEEK, expiryCode 1 = nearest weekly, 2 = next; k in -10..10, API max)
Re-running makes no network calls for files already cached. Empty answers are cached as header-only files.
"""
from __future__ import annotations
import sys, time
from datetime import date, timedelta
from common import *

SYMS = {"NIFTY": dict(sec=13, seg="NSE_FNO"), "SENSEX": dict(sec=51, seg="BSE_FNO")}
SPOT_FROM, SPOT_TO = date(2026, 10, 12), date(2026, 11, 13)
KS = range(-10, 11)
CODES = (1, 2)
SLEEP = 0.22

def spot_path(sym, day): return CACHE / f"spot_{sym}_{day}.csv"
def opt_path(sym, day, code, side, k): return CACHE / f"opt_{sym}_{day}_c{code}_{side}_k{k:+d}.csv"

def fetch_spot(c, sym, day, master):
    p = spot_path(sym, day)
    if p.exists(): return 0
    sid = resolve_index_id(master, sym)
    body = {"securityId": sid, "exchangeSegment": "IDX_I", "instrument": "INDEX", "interval": "1", "oi": False,
            "fromDate": f"{day} 09:00:00", "toDate": f"{day} 15:30:00"}
    r = c.post("/charts/intraday", body); time.sleep(SLEEP)
    ts = r.get("timestamp") or []
    df = pd.DataFrame({k: r[k] for k in ("open", "high", "low", "close", "volume")}) if ts else \
        pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    if ts:
        df.insert(0, "ts", pd.to_datetime(ts, unit="s", utc=True).tz_convert(IST).strftime("%Y-%m-%d %H:%M:%S"))
        df = df[(df.ts.str[11:16] >= "09:15") & (df.ts.str[11:16] < "15:30")]
    else:
        df.insert(0, "ts", [])
    df.to_csv(p, index=False); return 1

def fetch_opt(c, sym, day, code, side, k):
    p = opt_path(sym, day, code, side, k)
    if p.exists(): return 0
    s = SYMS[sym]
    strike = "ATM" if k == 0 else (f"ATM+{k}" if k > 0 else f"ATM{k}")
    body = {"exchangeSegment": s["seg"], "interval": "1", "securityId": s["sec"], "instrument": "OPTIDX",
            "expiryFlag": "WEEK", "expiryCode": code, "strike": strike,
            "drvOptionType": "CALL" if side == "CE" else "PUT",
            "requiredData": ["open", "high", "low", "close", "iv", "volume", "strike", "oi", "spot"],
            "fromDate": str(day), "toDate": str(day)}
    r = c.post("/charts/rollingoption", body); time.sleep(SLEEP)
    leg = (r.get("data") or {}).get("ce" if side == "CE" else "pe") or {}
    cols = ["timestamp", "open", "high", "low", "close", "iv", "volume", "oi", "strike", "spot"]
    df = pd.DataFrame({k_: leg.get(k_) or [] for k_ in cols})
    if len(df):
        df.insert(0, "ts", pd.DatetimeIndex(pd.to_datetime(df.pop("timestamp"), unit="s", utc=True)).tz_convert(IST).strftime("%Y-%m-%d %H:%M:%S"))
    else:
        df = df.drop(columns="timestamp"); df.insert(0, "ts", [])
    df.to_csv(p, index=False); return 1

def range_days():
    """EVERY trading day between the first and last date in signals.xlsx (not only days that have signals).
    A trading day = weekday on which Dhan returned a spot session (holidays come back empty)."""
    d = pd.read_excel(SIGNALS_XLSX); dts = pd.to_datetime(d.Date.dropna())
    lo, hi = dts.min().date(), dts.max().date()
    out, day = [], lo
    while day <= hi:
        if day.weekday() < 5:
            p = spot_path("NIFTY", day)
            if p.exists() and len(pd.read_csv(p)) > 0:
                out += [(sym, day) for sym in SYMS]
        day += timedelta(days=1)
    return set(out)

def main():
    c = DhanClient(load_config("v1")); master = load_scrip_master(load_config("v1"))
    n = 0
    try:
        day = SPOT_FROM
        while day <= SPOT_TO:
            if day.weekday() < 5:
                for sym in SYMS: n += fetch_spot(c, sym, day, master)
            day += timedelta(days=1)
        print(f"spot done ({n} calls)", flush=True)
        for sym, day in sorted(range_days(), key=lambda t: (t[1], t[0]), reverse=('--reverse' in sys.argv)):
            m = 0
            for code in CODES:
                for side in ("CE", "PE"):
                    for k in KS: m += fetch_opt(c, sym, day, code, side, k)
            n += m; print(f"{sym} {day}: {m} calls", flush=True)
    except TokenExpiredError:
        print("STOPPED: token expired. Put a fresh DHAN_ACCESS_TOKEN (and the full DHAN_CLIENT_ID) in backtest/.env and re-run."); sys.exit(2)
    print("done", n, "calls")

if __name__ == "__main__":
    main()
