"""The eight-check veto gate. Check functions are pure (no I/O, no globals); every threshold comes from cfg.

A check is a VETO, not a score: any single failure => SKIP. skip_reason lists every failed check ID.

  C1 sm5 >= th_trig             (tautological in own-scanner mode: candidates already satisfy it)
  C2 sm30 < th_exh              (SKIP when signed 30-min move >= th_exh)
  C3 trend == sgn  OR  flip active
  C4 rng_min < rng < rng_max    (strict both sides)
  C5 NOT (midday_start <= t < midday_end)
  C6 consecutive_sl < max_consec_sl  AND  not inside timeout
  C7 day_realised_pnl > day_brake    (strict; <= trips)
  C8 premium within per-index band, inclusive; premium unavailable -> "NA" (counts as pass, shown visibly)

NaN policy (agreed default): a NaN input needed by a check FAILS that check (warm-up bars are skipped and
logged as such, never silently passed). C8 is the only tri-state.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import time
from typing import Optional

import pandas as pd

PASS, FAIL, NA = "PASS", "FAIL", "NA"
CHECK_IDS = ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8"]
CAP_ID = "MAXTRADES"          # risk.max_trades_per_day guard (not one of the eight checks)


def _nan(x) -> bool:
    return x is None or (isinstance(x, float) and math.isnan(x))


def parse_hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


# ------------------------------------------------------------------ the eight checks (pure)
def c1_trigger(sm5: float, th_trig: float) -> bool:
    return (not _nan(sm5)) and sm5 >= th_trig


def c2_exhaustion(sm30: float, th_exh: float) -> bool:
    return (not _nan(sm30)) and sm30 < th_exh


def c3_trend(trend: float, sgn: int, flip_active: bool = False) -> bool:
    return flip_active or ((not _nan(trend)) and trend == sgn)


def c4_range(rng: float, rng_min: float, rng_max: float) -> bool:
    return (not _nan(rng)) and rng_min < rng < rng_max


def c5_time(t: time, start: time, end: time) -> bool:
    """Pass iff NOT (start <= t < end): 12:00:00 is inside (blocked), 13:00:00 is outside (allowed)."""
    return not (start <= t < end)


def c6_revenge(consecutive_sl: int, max_consec_sl: int, timeout_until: Optional[pd.Timestamp],
               now: pd.Timestamp) -> bool:
    inside_timeout = timeout_until is not None and now < timeout_until
    return consecutive_sl < max_consec_sl and not inside_timeout


def c7_day_brake(day_realised_pnl: float, day_brake: float) -> bool:
    return day_realised_pnl > day_brake


def c8_contract(premium: Optional[float], band: tuple[float, float]) -> Optional[bool]:
    """True/False, or None = NA (no premium available)."""
    if _nan(premium):
        return None
    return band[0] <= premium <= band[1]


# ------------------------------------------------------------------ data classes
@dataclass(frozen=True)
class Signal:
    index: str                 # "NIFTY" | "SENSEX"
    ts: pd.Timestamp           # sig_time (per features.signal_time)
    side: int                  # +1 = CE, -1 = PE
    m5: float
    m30: float
    rng: float
    trend: float
    close: float = float("nan")
    premium: Optional[float] = None      # supplied by the premium model (M4); None -> C8 = NA


@dataclass
class DayState:
    """Carried across signals within one trading day."""
    consecutive_sl: int = 0
    timeout_until: Optional[pd.Timestamp] = None
    realised_pnl: float = 0.0
    trades_taken: int = 0
    flip_side: int = 0
    flip_until: Optional[pd.Timestamp] = None

    def register_entry(self) -> None:
        self.trades_taken += 1

    def register_exit(self, pnl: float, is_sl: bool, exit_time: pd.Timestamp, cfg: dict) -> None:
        """Book a closed trade. A full stop-out increments the SL chain; anything else resets it.
        When the chain reaches max_consec_sl the 60-min timeout starts at exit_time and the chain is
        consumed (counter resets), so the timeout alone governs the pause."""
        g = cfg["gate"]
        self.realised_pnl += pnl
        if is_sl:
            self.consecutive_sl += 1
            if self.consecutive_sl >= g["max_consec_sl"]:
                self.timeout_until = exit_time + pd.Timedelta(minutes=g["timeout_minutes"])
                self.consecutive_sl = 0
        else:
            self.consecutive_sl = 0


@dataclass(frozen=True)
class Verdict:
    checks: dict               # {"C1": PASS|FAIL|NA, ...}
    verdict: str               # "TAKE" | "SKIP"
    skip_reason: str           # failed IDs joined by ";" ("" when TAKE)


# ------------------------------------------------------------------ flip rule (shipped DISABLED)
def flip_active(state: DayState, side: int, t: pd.Timestamp, cfg: dict) -> bool:
    return bool(cfg["flip_rule"]["enabled"] and state.flip_side == side
                and state.flip_until is not None and t < state.flip_until)


def maybe_start_flip(state: DayState, index: str, prev_close: float, close: float, day_open: float,
                     m5: float, t: pd.Timestamp, cfg: dict) -> bool:
    """A burst >= flip burst that crosses the day open grants a 30-min trend-bias override in its direction."""
    fr = cfg["flip_rule"]
    if not fr["enabled"] or _nan(m5) or _nan(prev_close) or abs(m5) < fr["burst"][index]:
        return False
    sgn = 1 if m5 > 0 else -1
    if (prev_close - day_open) * sgn < 0 < (close - day_open) * sgn:
        state.flip_side, state.flip_until = sgn, t + pd.Timedelta(minutes=fr["life_minutes"])
        return True
    return False


# ------------------------------------------------------------------ evaluation
def evaluate(sig: Signal, state: DayState, cfg: dict) -> Verdict:
    """Apply ALL eight checks (no short-circuit, so the ledger shows every result)."""
    g, ix, sgn = cfg["gate"], sig.index, sig.side
    sm5, sm30 = sig.m5 * sgn, sig.m30 * sgn
    c8 = c8_contract(sig.premium, tuple(g["premium_band"][ix]))
    res = {
        "C1": c1_trigger(sm5, g["th_trig"][ix]),
        "C2": c2_exhaustion(sm30, g["th_exh"][ix]),
        "C3": c3_trend(sig.trend, sgn, flip_active(state, sgn, sig.ts, cfg)),
        "C4": c4_range(sig.rng, g["rng_min"], g["rng_max"]),
        "C5": c5_time(sig.ts.time(), parse_hhmm(g["midday_start"]), parse_hhmm(g["midday_end"])),
        "C6": c6_revenge(state.consecutive_sl, g["max_consec_sl"], state.timeout_until, sig.ts),
        "C7": c7_day_brake(state.realised_pnl, g["day_brake"]),
        "C8": c8,
    }
    checks = {k: (NA if v is None else PASS if v else FAIL) for k, v in res.items()}
    failed = [k for k in CHECK_IDS if checks[k] == FAIL]
    if state.trades_taken >= cfg["risk"]["max_trades_per_day"]:
        failed.append(CAP_ID)
    return Verdict(checks, "SKIP" if failed else "TAKE", ";".join(failed))


# ------------------------------------------------------------------ own-scanner signal generation
def candidate_rows(feat: pd.DataFrame, index: str, cfg: dict) -> list[tuple[int, Signal]]:
    """On every 5-min bar close, |m5| >= th_trig is a candidate; direction = sign of the burst.
    `feat` is one day of compute_features() output. Returns (row position, Signal); premium attached later."""
    th = cfg["gate"]["th_trig"][index]
    out = []
    for i, r in enumerate(feat.itertuples(index=False)):
        if _nan(r.m5) or abs(r.m5) < th:
            continue
        out.append((i, Signal(index=index, ts=r.sig_time, side=1 if r.m5 > 0 else -1, m5=float(r.m5),
                              m30=float(r.m30), rng=float(r.rng), trend=float(r.trend), close=float(r.close))))
    return out


def generate_candidates(feat: pd.DataFrame, index: str, cfg: dict) -> list[Signal]:
    return [s for _, s in candidate_rows(feat, index, cfg)]
