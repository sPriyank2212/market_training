"""Weekly-expiry resolution (M4). Never hardcode a weekday.

Order of authority:
  1. Dhan instrument master (OPTIDX expiry dates)   - only lists FUTURE expiries, so it cannot cover October 2026 once those have expired;
  2. the exchange trading calendar: the index's weekly-expiry weekday, shifted back to the previous trading day when that day is a holiday
     (e.g. Tue 2026-10-20 Dussehra -> Mon 2026-10-19).
The result is then ASSERTED against the known dates in config (validation: expiries.known / known_outside_window). A mismatch raises.
Expiry time is 15:30 IST (data.market_close).
"""
from __future__ import annotations
from datetime import date, timedelta

import pandas as pd


class ExpiryAssertionError(RuntimeError):
    pass


def trading_days_between(store, symbol: str, start: date, end: date) -> set[date]:
    """Days with a real session (cache / Dhan). Weekends are never trading days."""
    out, d = set(), start
    while d <= end:
        if d.weekday() < 5 and not store.get_day(symbol, d).empty:
            out.add(d)
        d += timedelta(days=1)
    return out


def rule_expiries(weekday: int, start: date, end: date, trading: set[date], known_until: date) -> list[date]:
    """Dates (>= start, <= end) on `weekday`; a holiday shifts back to the previous trading day.
    Beyond `known_until` (no calendar knowledge) every weekday is assumed to be a trading day."""
    out, d = [], start
    while d <= end:
        if d.weekday() == weekday:
            e = d
            if d <= known_until:                    # calendar known: a non-trading expiry day moves to the previous trading day
                for _ in range(7):
                    if e in trading:
                        break
                    e -= timedelta(days=1)
            out.append(e)
        d += timedelta(days=1)
    return sorted(set(out))


def master_expiries(master: pd.DataFrame, index: str) -> list[date]:
    if master is None:
        return []
    m = master[(master["SEM_INSTRUMENT_NAME"] == "OPTIDX") & master["SEM_TRADING_SYMBOL"].astype(str).str.startswith(index + "-")]
    return sorted({pd.Timestamp(x).date() for x in m["SEM_EXPIRY_DATE"].dropna()})


def resolve_expiries(index: str, start: date, end: date, store, cfg: dict, master: pd.DataFrame | None = None) -> tuple[list[date], str]:
    """Weekly expiries covering [start, end + 21 days]. Returns (dates, source)."""
    horizon = end + timedelta(days=21)
    wd = cfg["synth"]["expiry_weekday"][index]
    cal_to = min(horizon, date.today())
    trading = trading_days_between(store, "NIFTY", start - timedelta(days=7), cal_to)
    dates = rule_expiries(wd, start, horizon, trading, known_until=cal_to)
    src = "trading calendar (weekday rule + holiday shift)"
    mx = [d for d in master_expiries(master, index) if start <= d <= horizon]
    if mx:                                         # master wins where it has data (live / not-yet-expired contracts)
        dates = sorted(set(dates) | set(mx)); src = "instrument master + trading calendar"
    return dates, src


def assert_known(index: str, dates: list[date], cfg: dict) -> pd.DataFrame:
    """Assert the resolved list contains every known expiry (and no unexpected one inside the known window)."""
    exp = cfg.get("expiries", {})
    known = [pd.Timestamp(x).date() for x in exp.get("known", {}).get(index, [])]
    outside = [pd.Timestamp(x).date() for x in exp.get("known_outside_window", {}).get(index, [])]
    rows, bad = [], []
    for k in sorted(known + outside):
        ok = k in dates
        rows.append(dict(index=index, expiry=k, weekday=k.strftime("%a"), asserted="in window" if k in known else "outside window", resolved=ok))
        if not ok:
            bad.append(k)
    if bad:
        raise ExpiryAssertionError(f"{index}: known expiries {[str(b) for b in bad]} not produced by resolution; resolved = {[str(d) for d in dates]}")
    return pd.DataFrame(rows)


def attach_expiries(cfg: dict, store, master: pd.DataFrame | None = None, verbose: bool = True) -> pd.DataFrame:
    """Resolve + assert expiries for both indices and store them in cfg['synth']['expiry_dates'] (used by premium.expiry_datetime)."""
    start, end = date.fromisoformat(cfg["run"]["start"]), date.fromisoformat(cfg["run"]["end"])
    cfg["synth"]["expiry_dates"] = {}
    tabs = []
    for ix in ("NIFTY", "SENSEX"):
        dates, src = resolve_expiries(ix, start, end, store, cfg, master)
        cfg["synth"]["expiry_dates"][ix] = dates
        t = assert_known(ix, dates, cfg) if cfg.get("expiries") else pd.DataFrame()
        tabs.append(t)
        if verbose:
            print(f"{ix}: expiries from {src}: {[f'{d:%a %Y-%m-%d}' for d in dates]}")
    return pd.concat(tabs, ignore_index=True)
