"""Black-Scholes sanity + contract helpers (M4 acceptance)."""
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
import premium as P
from candles import IST, compute_features
from dhan_client import load_config

CFG = load_config()
R, IV = CFG["synth"]["risk_free"], CFG["synth"]["iv"]["NIFTY"]


def test_atm_delta_about_half():
    T = 7 / 365
    dc = P.bs_delta(25000, 25000, T, R, IV, True)
    dp = P.bs_delta(25000, 25000, T, R, IV, False)
    # r = 6.5% puts the forward above spot, so spot-ATM call delta is ~0.53 (d1 = 0.078), not exactly 0.5
    assert 0.48 < dc < 0.56, dc
    assert -0.52 < dp < -0.44, dp
    assert abs((dc - dp) - 1.0) < 1e-12           # delta_call - delta_put = 1
    fwd = 25000 * np.exp(R * T)                    # at the FORWARD strike delta is ~0.5 (only the sigma^2 T/2 drift)
    assert abs(P.bs_delta(25000, fwd, T, R, IV, True) - 0.5) < 0.01


def test_put_call_parity():
    S, K, T = 25000, 25100, 4 / 365
    c, p = P.bs_price(S, K, T, R, IV, True), P.bs_price(S, K, T, R, IV, False)
    assert abs((c - p) - (S - K * np.exp(-R * T))) < 1e-8


def test_theta_visible_premium_falls_as_T_to_zero_spot_flat():
    Ts = np.array([7 / 365, 3 / 365, 1 / 365, 3 / (365 * 24), 1 / (365 * 24 * 60)])
    for is_call in (True, False):
        p = P.bs_price(np.full(5, 25000.0), 25000.0, Ts, R, IV, is_call)
        assert np.all(np.diff(p) < 0), p


def test_expiry_day_T_floor_no_nan():
    exp = P.expiry_datetime(date(2025, 10, 7), "NIFTY", CFG)
    now = pd.Series([exp, exp + pd.Timedelta(minutes=5)])                # at/after expiry
    T = P.years_to_expiry(now, exp, CFG)
    assert np.all(T > 0) and np.all(np.isfinite(P.bs_price(np.full(2, 25000.0), 25000.0, T, R, IV, True)))


def test_expiry_datetime_weekly_rule():
    f = lambda d, ix: P.expiry_datetime(d, ix, CFG)
    assert f(date(2025, 10, 6), "NIFTY") == pd.Timestamp("2025-10-07 15:30", tz=IST)    # Mon -> Tue
    assert f(date(2025, 10, 7), "NIFTY") == pd.Timestamp("2025-10-07 15:30", tz=IST)    # expiry day itself
    assert f(date(2025, 10, 8), "NIFTY") == pd.Timestamp("2025-10-14 15:30", tz=IST)    # Wed -> next Tue
    assert f(date(2025, 10, 6), "SENSEX") == pd.Timestamp("2025-10-09 15:30", tz=IST)   # Mon -> Thu


def test_strike_selection():
    assert P.strike_for(25012, +1, "NIFTY", CFG) == 25000
    assert P.strike_for(25030, +1, "NIFTY", CFG) == 25050
    assert P.strike_for(82049, -1, "SENSEX", CFG) == 82000
    cfg1 = {**CFG, "synth": {**CFG["synth"], "itm_steps": 1}}
    assert P.strike_for(25000, +1, "NIFTY", cfg1) == 24950       # CE ITM = lower strike
    assert P.strike_for(25000, -1, "NIFTY", cfg1) == 25050       # PE ITM = higher strike


def _flat_day(n=30, price=25000.0):
    ts = pd.date_range("2025-10-08 09:15", periods=n, freq="5min", tz=IST)
    df = pd.DataFrame({"ts": ts, "open": price, "high": price, "low": price, "close": price, "volume": 0})
    return compute_features(df, CFG)


def test_synth_path_theta_emerges_with_flat_spot_and_no_separate_term():
    feat = _flat_day()
    for side in (+1, -1):
        c, path = P.synth_path(feat, 0, side, "NIFTY", CFG)
        assert c.strike == 25000 and c.mode == "synth"
        assert np.all(np.diff(path.p_close) < 0)                  # decays purely because T shrinks
        assert np.allclose(path.p_high, path.p_close) and np.allclose(path.p_low, path.p_close)


def test_synth_bar_range_is_ordered_for_ce_and_pe():
    ts = pd.date_range("2025-10-08 09:15", periods=3, freq="5min", tz=IST)
    df = pd.DataFrame({"ts": ts, "open": 25000.0, "high": [25010.0] * 3, "low": [24990.0] * 3,
                       "close": 25000.0, "volume": 0})
    feat = compute_features(df, CFG)
    for side in (+1, -1):
        _, p = P.synth_path(feat, 0, side, "NIFTY", CFG)
        assert (p.p_high >= p.p_close).all() and (p.p_close >= p.p_low).all() and (p.p_high > p.p_low).all()
    _, ce = P.synth_path(feat, 0, +1, "NIFTY", CFG)
    _, pe = P.synth_path(feat, 0, -1, "NIFTY", CFG)
    assert ce.p_high.iloc[0] == P.bs_price(25010.0, 25000.0, P.years_to_expiry(feat.ts_close.iloc[0], P.expiry_datetime(date(2025, 10, 8), "NIFTY", CFG), CFG), R, IV, True)
    assert pe.p_high.iloc[0] > pe.p_close.iloc[0]                 # PE premium peaks when spot is at the LOW


def test_real_mode_failure_falls_back_to_synth_loudly(capsys):
    cfg = {**CFG, "mode": "real"}
    c, _ = P.get_path(_flat_day(), 0, +1, "NIFTY", cfg)
    assert c.mode == "synth"
    assert "WARNING" in capsys.readouterr().out
