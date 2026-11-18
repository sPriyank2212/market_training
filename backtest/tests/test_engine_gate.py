"""engine_gate mode: the same gate run on an externally supplied signal list (CSV date,time,index,side)."""
import copy
from datetime import date

import numpy as np
import pandas as pd

import backtest as B
from candles import IST
from dhan_client import load_config

CFG0 = load_config()
DAY = date(2026, 10, 12)


class Store:
    """NIFTY: flat 22500 with a +30-point burst on the bar starting 11:45; SENSEX: no session."""
    def get_day(self, sym, d):
        if sym != "NIFTY":
            return pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume"])
        ts = pd.date_range(f"{d} 09:15", periods=75, freq="5min", tz=IST)
        close = np.full(75, 22500.0)
        close[30:] += 50.0                       # bar 30 = 11:45: 22520 -> 22550 = burst of +30 (m5 = close - prior close)
        close[:30] += np.linspace(0, 20, 30)     # gentle drift up before it so trend is +1 by 11:45
        df = pd.DataFrame({"ts": ts, "open": close - 1, "high": close + 4, "low": close - 4, "close": close, "volume": 1})
        return df


def run(tmp_path, rows):
    p = tmp_path / "engine.csv"
    pd.DataFrame(rows, columns=["date", "time", "index", "side"]).to_csv(p, index=False)
    cfg = copy.deepcopy(CFG0)
    cfg["run"].update(scanner="engine_gate", engine_signals_csv=str(p))
    cfg["synth"]["expiry_dates"] = {"NIFTY": [date(2026, 10, 13)], "SENSEX": [date(2026, 10, 15)]}
    return pd.DataFrame(B.run_day(cfg, Store(), DAY, True))


def test_c1_is_meaningful_in_engine_mode(tmp_path):
    r = run(tmp_path, [("2026-10-12", "11:50", "NIFTY", "CE"), ("2026-10-12", "11:50", "NIFTY", "PE")])
    ce, pe = r[r.side == "CE"].iloc[0], r[r.side == "PE"].iloc[0]
    assert ce.C1 == "PASS" and ce.sm5 == 30.0
    assert pe.C1 == "FAIL" and "C1" in pe.skip_reason          # engine says PE but the market burst up: C1 can now veto


def test_signal_uses_last_completed_bar_no_lookahead(tmp_path):
    # 11:49 is INSIDE the 11:45 bar -> only bars with ts_close <= 11:49 are usable -> the 11:40 bar (m5 is small), not the burst bar
    r = run(tmp_path, [("2026-10-12", "11:49", "NIFTY", "CE")])
    assert r.iloc[0].sm5 != 30.0 and r.iloc[0].C1 == "FAIL"


def test_signal_before_first_completed_bar_is_nobar(tmp_path):
    r = run(tmp_path, [("2026-10-12", "09:16", "NIFTY", "CE")])
    assert r.iloc[0].verdict == "SKIP" and r.iloc[0].skip_reason == "NOBAR"


def test_missing_columns_rejected(tmp_path):
    p = tmp_path / "bad.csv"
    pd.DataFrame({"date": ["2026-10-12"], "time": ["11:50"]}).to_csv(p, index=False)
    cfg = copy.deepcopy(CFG0)
    cfg["run"].update(scanner="engine_gate", engine_signals_csv=str(p))
    try:
        B.load_engine_signals(cfg)
        assert False, "should have raised"
    except ValueError as e:
        assert "missing columns" in str(e)
