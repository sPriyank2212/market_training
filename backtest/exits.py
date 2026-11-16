"""Bracket exit simulator on a premium path (bar by bar).

  SL = entry*(1-sl_pct) (never widened) | T1 = entry*(1+t1_pct) | T2 = entry*(1+t2_pct)
  On T1 fill: `t1_fraction` of the position is sold at T1 and the stop on the REMAINDER moves to entry (cost).
  Force-flat at flatten_time at the close of the last bar completing by then.

Intra-bar tie-break (ruling): if one bar's range spans SL and T1 (or SL and T2) the SL fills FIRST.
After T1, if one bar spans the cost-stop and T2 the cost-stop fills first. Fills happen AT the level
(no slippage). In the bar that fills T1 the cost-stop does not yet exist, so it is not tested until the
next bar (assumption; a stricter same-bar variant would only lower P&L).

exit_reason: SL (full stop-out, no T1) | T1 (T1 filled, remainder stopped at cost) | T2 | EOD.
Only exit_reason == "SL" counts toward the C6 revenge chain.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class TradeResult:
    entry: float
    exit_ts: pd.Timestamp
    exit_reason: str
    pnl: float
    legs: list = field(default_factory=list)     # [(label, units, price)]
    t1_filled: bool = False
    exit_price: float = float("nan")             # average exit price over the position

    @property
    def is_sl(self) -> bool:
        return self.exit_reason == "SL"


def simulate_exit(entry: float, bars: pd.DataFrame, units: int, cfg: dict) -> TradeResult:
    """`bars`: premium bars AFTER the entry bar, columns ts_close, p_high, p_low, p_close, in time order."""
    e = cfg["exits"]
    if e["intrabar_tiebreak"] != "sl_first":
        raise ValueError("only intrabar_tiebreak=sl_first is implemented")
    sl, t1, t2 = entry * (1 - e["sl_pct"]), entry * (1 + e["t1_pct"]), entry * (1 + e["t2_pct"])
    flat = pd.Timestamp(f"{bars['ts_close'].iloc[0]:%Y-%m-%d} {e['flatten_time']}", tz=bars["ts_close"].iloc[0].tz) \
        if len(bars) else None
    t1_units = int(units * e["t1_fraction"])
    legs, left, t1_done, last = [], units, False, None

    def done(reason, ts):
        pnl = sum(u * (px - entry) for _, u, px in legs)
        avg = sum(u * px for _, u, px in legs) / units
        return TradeResult(entry, ts, reason, pnl, legs, t1_done, avg)

    for b in bars.itertuples(index=False):
        if b.ts_close > flat:
            break
        last = b
        if not t1_done:
            if b.p_low <= sl:                                   # SL first, even if the bar also spans T1/T2
                legs.append(("SL", left, sl))
                return done("SL", b.ts_close)
            if b.p_high >= t2:                                  # gapped through T1 and T2 in one bar
                legs += [("T1", t1_units, t1), ("T2", left - t1_units, t2)]
                t1_done = True
                return done("T2", b.ts_close)
            if b.p_high >= t1:
                legs.append(("T1", t1_units, t1))
                left -= t1_units
                t1_done = True                                   # cost-stop active from the NEXT bar
        else:
            if b.p_low <= entry:                                 # cost-stop first, even if bar also spans T2
                legs.append(("COST", left, entry))
                return done("T1", b.ts_close)
            if b.p_high >= t2:
                legs.append(("T2", left, t2))
                return done("T2", b.ts_close)
    if last is None:                                             # no bars before flatten time
        return TradeResult(entry, pd.NaT, "NOBARS", 0.0, [], False, entry)
    legs.append(("EOD", left, last.p_close))
    return done("EOD", last.ts_close)
