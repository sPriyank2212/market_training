import pandas as pd, pytest
from dhan_client import load_config
import validate as V

CFG = load_config("v3")

def _df(year=2026, n=75, close=100.0, high=101.0, low=99.0, open_=100.0):
    ts = pd.date_range(f"{year}-10-06 09:15", periods=n, freq="5min", tz="Asia/Kolkata")
    df = pd.DataFrame({"ts": ts, "open": open_, "high": 100.5, "low": 99.5, "close": close, "volume": 1})
    df.loc[0, "open"] = open_; df.loc[1, "high"] = high; df.loc[2, "low"] = low
    return df

ANCHOR = [100.0, 101.0, 99.0, 100.0]

def test_year_assert_fails_on_2025():
    with pytest.raises(V.ValidationError, match="YEAR ASSERT"):
        V.check_day(_df(year=2025), ANCHOR, CFG)

def test_year_assert_passes_2026():
    assert V.check_day(_df(), ANCHOR, CFG)["status"] == "OK"

def test_tolerance_boundary():
    tol = CFG["validation"]["tolerance_pct"] / 100
    ok = V.check_day(_df(close=100.0 * (1 + tol * 0.99)), ANCHOR, CFG)
    bad = V.check_day(_df(close=100.0 * (1 + tol * 1.5)), ANCHOR, CFG)
    assert ok["status"] == "OK" and bad["status"] == "FAIL" and bad["worst_field"] == "close"

def test_high_mismatch_fails():
    r = V.check_day(_df(high=101.0), [100.0, 101.5, 99.0, 100.0], CFG)
    assert r["status"] == "FAIL" and r["worst_field"] == "high"

def test_bar_count_rules():
    assert V.check_day(_df(n=75), ANCHOR, CFG)["status"] == "OK"
    assert V.check_day(_df(n=73), ANCHOR, CFG)["status"] == "WARN"
    assert V.check_day(_df(n=74), ANCHOR, CFG)["status"] == "WARN"
    assert V.check_day(_df(n=70), ANCHOR, CFG)["status"] == "FAIL"
    assert V.check_day(_df(n=76), ANCHOR, CFG)["status"] == "FAIL"

def test_anchor_table_complete():
    a = CFG["validation"]["anchors"]
    assert len(a) == 10 and all(set(v) == {"NIFTY", "SENSEX"} and all(len(x) == 4 for x in v.values()) for v in a.values())
    assert all(d.startswith("2026-") for d in a)


# ---- trading-window validation (user decision 2026-11-18) ----
def _pair(late_shift=0.0, window_shift=0.0, n=75):
    d = _df(n=n)
    d["close"] = 100.0
    y = d.set_index("ts")[["open", "high", "low", "close"]].copy()
    hh = y.index.strftime("%H:%M")
    y.loc[hh >= "15:20", ["open", "high", "low", "close"]] *= (1 + late_shift / 100)
    y.loc[hh == "10:00", "close"] *= (1 + window_shift / 100)
    return d, y

def test_window_ok_when_only_late_bars_differ():
    d, y = _pair(late_shift=0.5)
    c = V.compare_window(d, y, CFG)
    assert c["window_ok"] and c["late_warn"] and c["late"]["bad_bars"] == 2 and c["window"]["bad_bars"] == 0

def test_window_fails_when_a_window_bar_differs():
    d, y = _pair(window_shift=0.3)
    c = V.compare_window(d, y, CFG)
    assert not c["window_ok"] and c["window"]["bad_bars"] == 1

def test_window_boundary_1515_is_inside_window():
    d, y = _pair()
    y.loc[y.index.strftime("%H:%M") == "15:15", "close"] *= 1.01     # 1 % off at the 15:15 bar start
    assert not V.compare_window(d, y, CFG)["window_ok"]

def test_year_still_asserted_in_window_path():
    with pytest.raises(V.ValidationError):
        V.check_day(_df(year=2025), ANCHOR, CFG)
