"""Expiry resolution (M4) + dynamic ITM step."""
import copy
from datetime import date

import numpy as np
import pandas as pd
import pytest

import expiries as E
import premium as P
from candles import IST, compute_features
from dhan_client import load_config

CFG = load_config()


class FakeStore:
    """Calendar-only store: weekdays are sessions unless listed as holidays."""
    def __init__(self, holidays=()):
        self.h = {pd.Timestamp(x).date() for x in holidays}

    def get_day(self, symbol, d):
        return pd.DataFrame({"x": [1]}) if (d.weekday() < 5 and d not in self.h) else pd.DataFrame()


def cfg_for(start, end):
    c = copy.deepcopy(CFG)
    c["run"]["start"], c["run"]["end"] = start, end
    return c


def test_dussehra_shift_tuesday_holiday_moves_to_monday():
    store = FakeStore(holidays=["2026-10-20"])
    d, _ = E.resolve_expiries("NIFTY", date(2026, 10, 5), date(2026, 10, 17), store, cfg_for("2026-10-05", "2026-10-17"))
    assert date(2026, 10, 6) in d and date(2026, 10, 13) in d
    assert date(2026, 10, 19) in d and date(2026, 10, 20) not in d            # holiday-shifted to Monday


def test_sensex_thursdays():
    d, _ = E.resolve_expiries("SENSEX", date(2026, 10, 5), date(2026, 10, 17), FakeStore(), cfg_for("2026-10-05", "2026-10-17"))
    assert date(2026, 10, 8) in d and date(2026, 10, 15) in d and all(x.weekday() == 3 for x in d)


def test_known_dates_asserted_and_mismatch_raises():
    c = cfg_for("2026-10-05", "2026-10-17")
    store = FakeStore(holidays=["2026-10-20"])
    d, _ = E.resolve_expiries("NIFTY", date(2026, 10, 5), date(2026, 10, 17), store, c)
    assert E.assert_known("NIFTY", d, c).resolved.all()
    # without the holiday knowledge the Oct-19 expiry is NOT produced -> the assertion must fail loudly
    d2, _ = E.resolve_expiries("NIFTY", date(2026, 10, 5), date(2026, 10, 17), FakeStore(), c)
    with pytest.raises(E.ExpiryAssertionError):
        E.assert_known("NIFTY", d2, c)


def test_expiry_datetime_uses_resolved_list_and_nearest_on_or_after():
    c = copy.deepcopy(CFG)
    c["synth"]["expiry_dates"] = {"NIFTY": [date(2026, 10, 6), date(2026, 10, 13), date(2026, 10, 19), date(2026, 10, 27)]}
    f = lambda d: P.expiry_datetime(d, "NIFTY", c)
    assert f(date(2026, 10, 6)).date() == date(2026, 10, 6)       # expiry day itself -> same-day expiry
    assert f(date(2026, 10, 14)).date() == date(2026, 10, 19)     # holiday-shifted Monday, not Tuesday 20th
    assert f(date(2026, 10, 14)) == pd.Timestamp("2026-10-19 15:30", tz=IST)
    assert f(date(2026, 10, 20)).date() == date(2026, 10, 27)


def _feat(spot, day="2026-10-14"):
    n = 40
    ts = pd.date_range(f"{day} 09:15", periods=n, freq="5min", tz=IST)
    df = pd.DataFrame({"ts": ts, "open": spot, "high": spot + 5, "low": spot - 5, "close": spot, "volume": 1})
    return compute_features(df, CFG)


def test_dynamic_itm_steps_one_strike_when_atm_below_band():
    c = copy.deepcopy(CFG)
    c["synth"]["expiry_dates"] = {"NIFTY": [date(2026, 10, 14)], "SENSEX": [date(2026, 10, 15)]}      # expiry day -> ATM premium tiny (< 120)
    f = _feat(22500.0)
    ce, _ = P.synth_path(f, 20, +1, "NIFTY", c)
    pe, _ = P.synth_path(f, 20, -1, "NIFTY", c)
    assert ce.strike == 22450.0 and pe.strike == 22550.0          # ONE step ITM (CE lower, PE higher); never OTM


def test_dynamic_itm_stays_atm_when_premium_already_in_or_above_band():
    c = copy.deepcopy(CFG)
    c["synth"]["expiry_dates"] = {"NIFTY": [date(2026, 10, 20)]}                                       # 6 days out -> ATM premium well above 120
    f = _feat(22500.0)
    ce, path = P.synth_path(f, 20, +1, "NIFTY", c)
    assert ce.strike == 22500.0 and path.p_close.iloc[0] >= c["gate"]["premium_band"]["NIFTY"][0]


def test_dynamic_itm_off_keeps_atm():
    c = copy.deepcopy(CFG)
    c["synth"]["dynamic_itm"] = False
    c["synth"]["expiry_dates"] = {"NIFTY": [date(2026, 10, 14)]}
    ce, _ = P.synth_path(_feat(22500.0), 20, +1, "NIFTY", c)
    assert ce.strike == 22500.0
