"""Bracket exit tests incl. the SL-first intra-bar tie-break (M4 acceptance)."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from candles import IST
from dhan_client import load_config
from exits import simulate_exit

CFG = load_config()
E = 100.0
SL, T1, T2 = E * 0.85, E * 1.08, E * 1.25
UNITS = 100                       # t1_fraction 0.5 -> 50 / 50


def bars(rows, start="2025-10-08 10:00"):
    """rows: list of (low, high, close) per 5-min bar; ts_close = start + 5*(i+1) min."""
    ts = pd.date_range(start, periods=len(rows), freq="5min", tz=IST) + pd.Timedelta(minutes=5)
    return pd.DataFrame({"ts_close": ts, "p_low": [r[0] for r in rows], "p_high": [r[1] for r in rows],
                         "p_close": [r[2] for r in rows]})


def test_plain_stop_loss():
    r = simulate_exit(E, bars([(SL - 1, 101, 90)]), UNITS, CFG)
    assert r.exit_reason == "SL" and r.is_sl and r.pnl == pytest.approx(UNITS * (SL - E)) and not r.t1_filled


def test_bar_spanning_SL_and_T1_fills_SL_first():
    r = simulate_exit(E, bars([(SL - 0.5, T1 + 0.5, 100)]), UNITS, CFG)
    assert r.exit_reason == "SL" and r.pnl == pytest.approx(UNITS * (SL - E)) and not r.t1_filled


def test_bar_spanning_SL_and_T2_fills_SL_first():
    r = simulate_exit(E, bars([(SL - 0.5, T2 + 5, 110)]), UNITS, CFG)
    assert r.exit_reason == "SL" and not r.t1_filled and r.pnl < 0


def test_T1_then_T2():
    r = simulate_exit(E, bars([(99, T1 + 0.1, 105), (104, T2 + 0.1, 120)]), UNITS, CFG)
    assert r.exit_reason == "T2" and r.t1_filled
    assert r.pnl == pytest.approx(50 * (T1 - E) + 50 * (T2 - E))


def test_T1_then_remainder_stopped_at_cost():
    r = simulate_exit(E, bars([(99, T1 + 0.1, 105), (E - 0.1, 106, 101)]), UNITS, CFG)
    assert r.exit_reason == "T1" and not r.is_sl and r.t1_filled
    assert r.pnl == pytest.approx(50 * (T1 - E))                   # remainder out at cost = 0


def test_after_T1_bar_spanning_cost_stop_and_T2_fills_cost_first():
    r = simulate_exit(E, bars([(99, T1 + 0.1, 105), (E - 0.1, T2 + 1, 120)]), UNITS, CFG)
    assert r.exit_reason == "T1" and r.pnl == pytest.approx(50 * (T1 - E))


def test_gap_through_T1_and_T2_in_one_bar():
    r = simulate_exit(E, bars([(99, T2 + 1, 120)]), UNITS, CFG)
    assert r.exit_reason == "T2" and r.pnl == pytest.approx(50 * (T1 - E) + 50 * (T2 - E))


def test_sl_never_widened_after_t1_stays_at_cost_not_back_to_original_sl():
    # after T1, a dip to 0.9*E (above original SL, below cost) must stop at COST, not ride to SL
    r = simulate_exit(E, bars([(99, T1 + 0.1, 105), (90, 104, 95)]), UNITS, CFG)
    assert r.exit_reason == "T1" and r.exit_price > E * 0.9


def test_T1_bar_does_not_test_cost_stop_until_next_bar():
    # bar fills T1 and also trades down to cost level -> assumption: stop only active from next bar
    r = simulate_exit(E, bars([(E - 1, T1 + 0.1, 104), (102, 105, 103)]), UNITS, CFG)
    assert r.t1_filled and r.exit_reason == "EOD"


def test_EOD_flat_at_1515_uses_last_bar_completing_by_then_and_ignores_later_bars():
    rows = [(99, 104, 101)] * 6 + [(10, 200, 150)] * 3             # bars after 15:15 must be ignored
    r = simulate_exit(E, bars(rows, start="2025-10-08 14:45"), UNITS, CFG)
    assert r.exit_reason == "EOD" and r.exit_ts == pd.Timestamp("2025-10-08 15:15", tz=IST)
    assert r.pnl == pytest.approx(UNITS * (101 - E))


def test_EOD_after_T1_sells_only_remainder_at_close():
    rows = [(99, T1 + 0.1, 105)] + [(102, 106, 103)] * 3
    r = simulate_exit(E, bars(rows, start="2025-10-08 15:00"), UNITS, CFG)
    assert r.exit_reason == "EOD" and r.pnl == pytest.approx(50 * (T1 - E) + 50 * (103 - E))


def test_other_tiebreak_value_rejected():
    cfg = {**CFG, "exits": {**CFG["exits"], "intrabar_tiebreak": "target_first"}}
    with pytest.raises(ValueError):
        simulate_exit(E, bars([(99, 101, 100)]), UNITS, cfg)
