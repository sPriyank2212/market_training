"""Gate unit tests — the M3 acceptance criteria."""
import copy
import sys
from dataclasses import replace
from datetime import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import gate as G
from candles import IST, compute_features
from dhan_client import load_config
from gate import DayState, Signal, evaluate

CFG = load_config()


def ts(hhmm: str) -> pd.Timestamp:
    return pd.Timestamp(f"2025-10-06 {hhmm}", tz=IST)


def base(**kw) -> Signal:
    """A NIFTY CE signal that passes all eight checks."""
    d = dict(index="NIFTY", ts=ts("10:30:00"), side=1, m5=25.0, m30=10.0, rng=0.5, trend=1.0,
             close=25000.0, premium=150.0)
    d.update(kw)
    return Signal(**d)


def run(sig=None, state=None, cfg=CFG):
    return evaluate(sig or base(), state or DayState(), cfg)


def sl_twice(state, t0="10:00:00"):
    t = ts(t0)
    state.register_exit(-1000, True, t, CFG)
    state.register_exit(-1000, True, t + pd.Timedelta(minutes=5), CFG)
    return t + pd.Timedelta(minutes=5)           # time of the 2nd stop-out


# ----------------------------------------------------------------- baseline + each check fails individually
def test_baseline_takes():
    v = run()
    assert v.verdict == "TAKE" and v.skip_reason == ""
    assert all(v.checks[k] == "PASS" for k in G.CHECK_IDS)


@pytest.mark.parametrize("cid,sig,state", [
    ("C1", base(m5=19.0), None),                               # sm5 below th_trig(20)
    ("C2", base(m30=40.0), None),                              # sm30 == th_exh -> SKIP (>=)
    ("C3", base(trend=-1.0), None),                            # trend against side
    ("C4", base(rng=0.90), None),
    ("C5", base(ts=ts("12:30:00")), None),
    ("C6", base(), "timeout"),
    ("C7", base(), "brake"),
    ("C8", base(premium=100.0), None),
])
def test_each_check_fails_individually(cid, sig, state):
    st = DayState()
    if state == "timeout":
        sl_twice(st, "10:00:00")                               # timeout runs to 11:05
        sig = base(ts=ts("10:30:00"))
    if state == "brake":
        st.realised_pnl = -7000
    v = evaluate(sig, st, CFG)
    assert v.verdict == "SKIP"
    assert v.skip_reason == cid, v
    assert v.checks[cid] == "FAIL"
    assert all(v.checks[k] != "FAIL" for k in G.CHECK_IDS if k != cid)   # only that one failed


def test_multiple_failures_all_listed():
    v = run(base(m30=50.0, rng=0.95, ts=ts("12:10:00")))
    assert v.skip_reason == "C2;C4;C5"


# ----------------------------------------------------------------- C1 pure function
def test_c1_pure():
    assert G.c1_trigger(20, 20) and not G.c1_trigger(19.99, 20) and not G.c1_trigger(float("nan"), 20)


# ----------------------------------------------------------------- signed handling for PE
def test_pe_signs():
    pe = base(side=-1, m5=-25.0, m30=-10.0, trend=-1.0)
    assert run(pe).verdict == "TAKE"
    assert run(replace(pe, m30=-45.0)).skip_reason == "C2"     # building 30-min move in trade direction
    assert run(replace(pe, m30=+45.0)).verdict == "TAKE"       # 30-min move AGAINST the trade is not exhaustion
    assert run(replace(pe, trend=1.0)).skip_reason == "C3"


def test_c2_uses_per_index_thresholds():
    assert run(base(index="SENSEX", m5=70.0, m30=129.0, premium=400.0)).verdict == "TAKE"
    assert run(base(index="SENSEX", m5=70.0, m30=130.0, premium=400.0)).skip_reason == "C2"


# ----------------------------------------------------------------- C4 range (strict)
def test_c4_boundaries():
    assert run(base(rng=0.90)).skip_reason == "C4"
    assert run(base(rng=0.85)).skip_reason == "C4"             # strict
    assert run(base(rng=0.15)).skip_reason == "C4"             # strict
    assert run(base(rng=0.8499)).verdict == "TAKE" and run(base(rng=0.1501)).verdict == "TAKE"


# ----------------------------------------------------------------- C5 midday + exact edges
def test_c5_midday_and_edges():
    assert run(base(ts=ts("12:30:00"))).skip_reason == "C5"
    assert run(base(ts=ts("12:00:00"))).skip_reason == "C5"    # 12:00:00 inside  -> SKIP
    assert run(base(ts=ts("12:59:59"))).skip_reason == "C5"
    assert run(base(ts=ts("13:00:00"))).verdict == "TAKE"      # 13:00:00 outside -> allowed
    assert run(base(ts=ts("11:59:59"))).verdict == "TAKE"
    assert G.c5_time(time(12, 0), time(12, 0), time(13, 0)) is False
    assert G.c5_time(time(13, 0), time(12, 0), time(13, 0)) is True


# ----------------------------------------------------------------- C6 revenge chain + 60-min timeout
def test_c6_two_consecutive_sl_trigger_60min_timeout():
    st = DayState()
    t2 = sl_twice(st, "10:00:00")                              # 2nd SL at 10:05 -> timeout until 11:05
    assert st.timeout_until == t2 + pd.Timedelta(minutes=60)
    for hhmm in ("10:06:00", "10:30:00", "11:04:59"):
        assert evaluate(base(ts=ts(hhmm)), st, CFG).skip_reason == "C6", hhmm
    assert evaluate(base(ts=ts("11:05:00")), st, CFG).verdict == "TAKE"   # timeout over exactly at +60 min


def test_c6_single_sl_does_not_trip_and_win_resets_chain():
    st = DayState()
    st.register_exit(-1000, True, ts("10:00:00"), CFG)
    assert st.consecutive_sl == 1 and evaluate(base(), st, CFG).verdict == "TAKE"
    st.register_exit(+500, False, ts("10:20:00"), CFG)          # a non-SL exit resets the chain
    st.register_exit(-1000, True, ts("10:25:00"), CFG)
    assert st.consecutive_sl == 1 and st.timeout_until is None


def test_c6_counter_alone_also_vetoes():
    st = DayState(consecutive_sl=2)                             # spec form: consecutive_sl < 2
    assert evaluate(base(), st, CFG).skip_reason == "C6"


# ----------------------------------------------------------------- C7 day brake: exact boundary
def test_c7_exact_boundary():
    assert evaluate(base(), DayState(realised_pnl=-7000), CFG).skip_reason == "C7"    # SKIP at exactly -7000
    assert evaluate(base(), DayState(realised_pnl=-7000.01), CFG).skip_reason == "C7"
    assert evaluate(base(), DayState(realised_pnl=-6999), CFG).verdict == "TAKE"      # -6999 passes
    assert G.c7_day_brake(-7000, -7000) is False and G.c7_day_brake(-6999.99, -7000) is True


def test_c7_brake_arrives_via_register_exit():
    st = DayState()
    st.register_exit(-3500, False, ts("10:00:00"), CFG)
    st.register_exit(-3500, False, ts("10:30:00"), CFG)
    assert st.realised_pnl == -7000 and evaluate(base(ts=ts("11:00:00")), st, CFG).skip_reason == "C7"


# ----------------------------------------------------------------- C8 band
def test_c8_band_inclusive_both_sides_and_per_index():
    assert run(base(premium=119.99)).skip_reason == "C8"
    assert run(base(premium=120.0)).verdict == "TAKE" and run(base(premium=215.0)).verdict == "TAKE"
    assert run(base(premium=215.01)).skip_reason == "C8"
    sx = dict(index="SENSEX", m5=70.0, m30=10.0)
    assert run(base(premium=300.0, **sx)).verdict == "TAKE" and run(base(premium=460.1, **sx)).skip_reason == "C8"
    # same band for CE and PE
    assert run(base(side=-1, m5=-25.0, m30=-10.0, trend=-1.0, premium=150.0)).verdict == "TAKE"


def test_c8_na_passes_visibly():
    v = run(base(premium=None))
    assert v.checks["C8"] == "NA" and v.verdict == "TAKE" and v.skip_reason == ""


# ----------------------------------------------------------------- NaN warm-up policy
def test_nan_inputs_fail_their_check():
    nan = float("nan")
    assert run(base(trend=nan)).skip_reason == "C3"
    assert run(base(m30=nan)).skip_reason == "C2"
    assert run(base(rng=nan)).skip_reason == "C4"


# ----------------------------------------------------------------- flip rule (disabled by default)
def test_flip_disabled_by_default_cannot_override():
    st = DayState(flip_side=1, flip_until=ts("11:00:00"))
    assert CFG["flip_rule"]["enabled"] is False
    assert evaluate(base(trend=-1.0), st, CFG).skip_reason == "C3"


def test_flip_when_enabled():
    cfg = copy.deepcopy(CFG)
    cfg["flip_rule"]["enabled"] = True
    st = DayState()
    started = G.maybe_start_flip(st, "NIFTY", prev_close=24990, close=25010, day_open=25000, m5=35, t=ts("10:30:00"), cfg=cfg)
    assert started and st.flip_side == 1
    assert evaluate(base(ts=ts("10:50:00"), trend=-1.0), st, cfg).verdict == "TAKE"        # inside 30-min life
    assert evaluate(base(ts=ts("11:00:00"), trend=-1.0), st, cfg).skip_reason == "C3"      # expired at +30
    assert not G.maybe_start_flip(DayState(), "NIFTY", 24990, 25010, 25000, 25, ts("10:30:00"), cfg)  # burst < 30


# ----------------------------------------------------------------- daily cap + scanner
def test_max_trades_cap():
    st = DayState(trades_taken=CFG["risk"]["max_trades_per_day"])
    assert evaluate(base(), st, CFG).skip_reason == G.CAP_ID


def test_generate_candidates_direction_and_threshold():
    closes = [100, 100, 130, 130, 95, 95, 95, 95]          # +30 burst, then -35 burst
    n = len(closes)
    df = pd.DataFrame({"ts": pd.date_range("2025-10-06 09:15", periods=n, freq="5min", tz=IST),
                       "open": closes, "high": np.array(closes) + 1, "low": np.array(closes) - 1,
                       "close": closes, "volume": 0})
    sigs = G.generate_candidates(compute_features(df, CFG), "NIFTY", CFG)
    assert [s.side for s in sigs] == [1, -1] and [s.m5 for s in sigs] == [30.0, -35.0]
    assert G.generate_candidates(compute_features(df, CFG), "SENSEX", CFG) == []   # below SENSEX trigger (60)
