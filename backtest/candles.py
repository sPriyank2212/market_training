"""5-min index candles: Dhan fetch, per-day CSV cache, file-based fallback, feature engine.

Lookup order in CandleStore.get_day():  cache  ->  Dhan API  ->  manual CSV (data/manual/).
Every returned frame carries a `source` column ("dhan" | "file") so reports can say where each day came from.
All timestamps are tz-aware IST, stamped at BAR START (09:15 = first bar of the session).
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from dhan_client import DhanClient, TokenExpiredError, load_config

ROOT = Path(__file__).parent
IST = "Asia/Kolkata"
BASE_COLS = ["ts", "open", "high", "low", "close", "volume"]


# ================================================================= instrument master
def load_scrip_master(cfg: dict, refresh: bool = False) -> pd.DataFrame:
    """Download (once) and cache the Dhan instrument master CSV. Static public file, GET only."""
    path = ROOT / cfg["data"]["scrip_master_path"]
    if refresh or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        r = requests.get(cfg["data"]["scrip_master_url"], timeout=60)
        r.raise_for_status()
        path.write_bytes(r.content)
    return pd.read_csv(path, low_memory=False)


def resolve_index_id(master: pd.DataFrame, symbol: str) -> str:
    """Find the securityId of an index (NIFTY / SENSEX) from index rows. Never hardcoded."""
    df = master[master["SEM_INSTRUMENT_NAME"].astype(str).str.upper() == "INDEX"]
    for col in ("SEM_TRADING_SYMBOL", "SEM_CUSTOM_SYMBOL"):
        hit = df[df[col].astype(str).str.upper().str.strip() == symbol.upper()]
        if len(hit):
            return str(int(hit.iloc[0]["SEM_SMST_SECURITY_ID"]))
    names = sorted(df["SEM_TRADING_SYMBOL"].astype(str).unique())[:40]
    raise LookupError(f"Index {symbol!r} not found in scrip master. Index symbols seen: {names}")


# ================================================================= sources
def _empty() -> pd.DataFrame:
    return pd.DataFrame(columns=BASE_COLS)


def _session_filter(df: pd.DataFrame, day: date, cfg: dict) -> pd.DataFrame:
    t = df["ts"].dt.strftime("%H:%M")
    keep = (df["ts"].dt.date == day) & (t >= cfg["data"]["market_open"]) & (t < cfg["data"]["market_close"])
    return df[keep].sort_values("ts").reset_index(drop=True)


def fetch_day_dhan(client: DhanClient, cfg: dict, security_id: str, day: date) -> pd.DataFrame | None:
    """One day of 5-min index candles from POST /charts/intraday.

    Returns: DataFrame (possibly EMPTY = Dhan answered, no data, e.g. holiday)
             None                    = request failed (do NOT treat as "no trading that day").
    Docs: fromDate/toDate are 'YYYY-MM-DD HH:MM:SS'; fromDate is exclusive at the boundary
    (verified live), so we start at data.fetch_from and filter to the session.
    """
    body = {
        "securityId": security_id, "exchangeSegment": "IDX_I", "instrument": "INDEX",
        "interval": str(cfg["data"]["interval_minutes"]), "oi": False,
        "fromDate": f"{day:%Y-%m-%d} {cfg['data']['fetch_from']}:00",
        "toDate": f"{day:%Y-%m-%d} {cfg['data']['market_close']}:00",
    }
    try:
        resp = client.post("/charts/intraday", body)
    except TokenExpiredError:
        raise
    except Exception as e:
        print(f"  [{day}] Dhan request failed: {e}")
        return None
    ts = resp.get("timestamp") or []
    if not ts:
        return _empty()
    df = pd.DataFrame({k: resp[k] for k in ("open", "high", "low", "close", "volume")})
    df["ts"] = pd.to_datetime(ts, unit="s", utc=True).tz_convert(IST)
    return _session_filter(df[BASE_COLS], day, cfg)


class FileSource:
    """File-based CandleSource: reads data/manual/{SYMBOL}_{YYYY-MM-DD}.csv.
    Columns: ts (ISO datetime, IST), open, high, low, close[, volume]. Use for days Dhan can't serve
    (e.g. Yahoo/other exports the user drops in)."""

    def __init__(self, directory: Path):
        self.dir = directory

    def get_day(self, symbol: str, day: date, cfg: dict) -> pd.DataFrame | None:
        p = self.dir / f"{symbol}_{day:%Y-%m-%d}.csv"
        if not p.exists():
            return None
        df = pd.read_csv(p)
        ts = pd.to_datetime(df["ts"])
        df["ts"] = ts.dt.tz_localize(IST) if ts.dt.tz is None else ts.dt.tz_convert(IST)
        if "volume" not in df:
            df["volume"] = 0
        return _session_filter(df[BASE_COLS], day, cfg)


class CandleStore:
    """cache -> Dhan -> manual file. Re-runs of cached days make no network calls."""

    def __init__(self, cfg: dict | None = None, client: DhanClient | None = None, offline: bool = False):
        self.cfg = cfg or load_config()
        self.cache = ROOT / self.cfg["data"]["cache_dir"]
        self.cache.mkdir(parents=True, exist_ok=True)
        self.files = FileSource(ROOT / self.cfg["data"]["manual_dir"])
        self.offline = offline
        self._client = client
        self._master: pd.DataFrame | None = None
        self._ids: dict[str, str] = {}
        self.network_calls = 0

    # -- helpers
    def _client_(self) -> DhanClient:
        if self._client is None:
            self._client = DhanClient(self.cfg)
        return self._client

    def _sec_id(self, symbol: str) -> str:
        if symbol not in self._ids:
            if self._master is None:
                self._master = load_scrip_master(self.cfg)
            self._ids[symbol] = resolve_index_id(self._master, symbol)
        return self._ids[symbol]

    def _csv(self, symbol: str, day: date) -> Path:
        return self.cache / f"{symbol}_{day:%Y-%m-%d}.csv"

    def _nodata(self, symbol: str, day: date) -> Path:
        return self.cache / f"{symbol}_{day:%Y-%m-%d}.nodata"

    def _read_cache(self, symbol: str, day: date) -> pd.DataFrame:
        df = pd.read_csv(self._csv(symbol, day))
        df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(IST)
        return df

    # -- main entry
    def get_day(self, symbol: str, day: date) -> pd.DataFrame:
        """Candles for one day; EMPTY frame = not a trading day / no data."""
        if day.weekday() >= 5:
            return _empty()
        if self._nodata(symbol, day).exists():
            return _empty()
        if self._csv(symbol, day).exists():
            return self._read_cache(symbol, day)

        df, source = None, "dhan"
        if not self.offline:
            self.network_calls += 1
            df = fetch_day_dhan(self._client_(), self.cfg, self._sec_id(symbol), day)
            if df is not None and df.empty:               # Dhan answered: confirmed no session (holiday)
                self._nodata(symbol, day).write_text("holiday/no-data confirmed by Dhan\n")
                return _empty()
        if df is None:                                    # Dhan failed or offline -> manual file fallback
            df, source = self.files.get_day(symbol, day, self.cfg), "file"
            if df is None or df.empty:
                print(f"  [{symbol} {day}] no candles available (Dhan unreachable, no manual file)")
                return _empty()
            print(f"  [{symbol} {day}] using manual file fallback")
        df = df.copy()
        df["source"] = source
        df.to_csv(self._csv(symbol, day), index=False)
        return df

    def fetch_range(self, symbol: str, start: date, end: date, chunk_days: int = 80) -> dict:
        """Bulk-fill the cache with few API calls (Dhan allows <=90 days per intraday call).
        Weekdays absent from a VALID response are cached as holidays; a failed chunk caches nothing."""
        stats = {"chunks": 0, "days_written": 0, "holidays": 0, "failed_chunks": 0}
        d = start
        while d <= end:
            c_end = min(d + timedelta(days=chunk_days - 1), end)
            wd = [d + timedelta(days=k) for k in range((c_end - d).days + 1) if (d + timedelta(days=k)).weekday() < 5]
            todo = [x for x in wd if not (self._csv(symbol, x).exists() or self._nodata(symbol, x).exists())]
            if todo:
                body = {"securityId": self._sec_id(symbol), "exchangeSegment": "IDX_I", "instrument": "INDEX",
                        "interval": str(self.cfg["data"]["interval_minutes"]), "oi": False,
                        "fromDate": f"{d:%Y-%m-%d} {self.cfg['data']['fetch_from']}:00",
                        "toDate": f"{c_end:%Y-%m-%d} {self.cfg['data']['market_close']}:00"}
                stats["chunks"] += 1
                self.network_calls += 1
                try:
                    resp = self._client_().post("/charts/intraday", body)
                except TokenExpiredError:
                    raise
                except Exception as e:
                    print(f"  [{symbol} {d}..{c_end}] chunk failed: {e}")
                    stats["failed_chunks"] += 1
                    d = c_end + timedelta(days=1)
                    continue
                ts = resp.get("timestamp") or []
                allb = pd.DataFrame({k: resp[k] for k in ("open", "high", "low", "close", "volume")}) if ts else _empty()
                if ts:
                    allb["ts"] = pd.to_datetime(ts, unit="s", utc=True).tz_convert(IST)
                for x in todo:
                    day_df = _session_filter(allb[BASE_COLS], x, self.cfg) if ts else _empty()
                    if day_df.empty:
                        self._nodata(symbol, x).write_text("holiday/no-data confirmed by Dhan (range fetch)\n")
                        stats["holidays"] += 1
                    else:
                        day_df = day_df.assign(source="dhan")
                        day_df.to_csv(self._csv(symbol, x), index=False)
                        stats["days_written"] += 1
            d = c_end + timedelta(days=1)
        return stats

    def trading_days(self, symbol: str, start: date, end: date) -> list[date]:
        out, d = [], start
        while d <= end:
            if not self.get_day(symbol, d).empty:
                out.append(d)
            d += timedelta(days=1)
        return out


# ================================================================= feature engine
def compute_features(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Per-day features from 5-min bars (one trading day in, same rows out). No look-ahead:
    every value on row i uses bars <= i only.

      m5    = close - close[5 min ago]            NaN until enough bars exist (lookback is within-day only)
      m30   = close - close[30 min ago]
      trend = sign(close - close[60 min ago])
      rng   = (close - day_low)/(day_high - day_low), running day high/low from BAR HIGHS/LOWS up to and
              including this bar; 0.5 when high == low (divide-by-zero guard)
      ts_close = ts + interval (when the bar actually completes); sig_time = ts or ts_close per
                 features.signal_time ("bar_start" | "bar_close") — the stamp C5/C6 use.
    """
    f, step = cfg["features"], cfg["data"]["interval_minutes"]
    d = df.sort_values("ts").reset_index(drop=True).copy()
    c = d["close"]
    d["ts_close"] = d["ts"] + pd.Timedelta(minutes=step)
    d["sig_time"] = d["ts"] if f["signal_time"] == "bar_start" else d["ts_close"]
    d["day_open"] = d["open"].iloc[0]
    d["day_high"] = d["high"].cummax()
    d["day_low"] = d["low"].cummin()
    d["m5"] = c - c.shift(f["m5_minutes"] // step)
    d["m30"] = c - c.shift(f["m30_minutes"] // step)
    span = d["day_high"] - d["day_low"]
    d["rng"] = np.where(span > 0, (c - d["day_low"]) / span.where(span > 0, 1), 0.5)
    d["trend"] = np.sign(c - c.shift(f["trend_minutes"] // step))
    return d


# ================================================================= M1 acceptance + M2 demo
def main(argv: list[str]) -> int:
    cfg = load_config()
    symbol = argv[0] if argv else "NIFTY"
    store = CandleStore(cfg)
    start, end = date.fromisoformat(cfg["run"]["start"]), date.fromisoformat(cfg["run"]["end"])
    days = store.trading_days(symbol, start, end)
    print(f"{symbol}: trading days {start}..{end}: {[d.isoformat() for d in days]}  "
          f"(network calls this run: {store.network_calls})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
