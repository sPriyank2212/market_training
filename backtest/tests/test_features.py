import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from candles import IST, FileSource, compute_features
from dhan_client import load_config

CFG = load_config()


def _day(closes, highs=None, lows=None):
    n = len(closes)
    ts = pd.date_range("2025-10-06 09:15", periods=n, freq="5min", tz=IST)
    c = pd.Series(closes, dtype=float)
    return pd.DataFrame({"ts": ts, "open": c, "high": highs if highs is not None else c + 1,
                         "low": lows if lows is not None else c - 1, "close": c, "volume": 0})


def test_lookbacks_and_nan_warmup():
    f = compute_features(_day(list(range(100, 120))), CFG)
    assert np.isnan(f.m5.iloc[0]) and f.m5.iloc[1] == 1
    assert np.isnan(f.m30.iloc[5]) and f.m30.iloc[6] == 6
    assert np.isnan(f.trend.iloc[11]) and f.trend.iloc[12] == 1


def test_no_lookahead():
    closes = list(range(100, 120))
    full = compute_features(_day(closes), CFG)
    part = compute_features(_day(closes[:10]), CFG)
    for col in ("m5", "m30", "rng", "day_high", "day_low", "trend"):
        pd.testing.assert_series_equal(full[col].iloc[:10], part[col], check_names=False)


def test_rng_running_high_low_and_zero_span_guard():
    f = compute_features(_day([100, 100], highs=[100, 100], lows=[100, 100]), CFG)
    assert (f.rng == 0.5).all()                      # high == low -> guarded, no divide-by-zero
    g = compute_features(_day([100, 110, 105], highs=[101, 111, 106], lows=[99, 109, 104]), CFG)
    assert g.day_high.tolist() == [101, 111, 111] and g.day_low.tolist() == [99, 99, 99]
    assert abs(g.rng.iloc[2] - (105 - 99) / (111 - 99)) < 1e-12


def test_sig_time_switch():
    df = _day([100, 101])
    f = compute_features(df, CFG)                    # default bar_start
    assert f.sig_time.iloc[0] == df.ts.iloc[0]
    cfg2 = {**CFG, "features": {**CFG["features"], "signal_time": "bar_close"}}
    assert compute_features(df, cfg2).sig_time.iloc[0] == df.ts.iloc[0] + pd.Timedelta(minutes=5)


def test_file_source_roundtrip(tmp_path):
    day = pd.Timestamp("2025-10-06").date()
    df = _day([100, 101, 102])
    out = df.assign(ts=df.ts.dt.strftime("%Y-%m-%d %H:%M:%S"))[["ts", "open", "high", "low", "close"]]
    out.to_csv(tmp_path / "NIFTY_2025-10-06.csv", index=False)
    got = FileSource(tmp_path).get_day("NIFTY", day, CFG)
    assert len(got) == 3 and str(got.ts.iloc[0].tz) == IST
    assert FileSource(tmp_path).get_day("NIFTY", pd.Timestamp("2025-10-07").date(), CFG) is None
