"""Premium model.

SYNTH (default): Black-Scholes on the index spot path. Theta is NOT added separately — it emerges from
T shrinking bar by bar. Contract (strike) is fixed at entry from the entry-bar spot.
REAL: Dhan expired/rolling option history (see RealPremium) — falls back to SYNTH loudly if unavailable.

Per-bar premium range: for a fixed strike and the bar's end-time T, premium is monotonic in spot, so a
bar's premium high/low come from the bar's spot high/low (CE: high<-spot high; PE: high<-spot low).
This gives the exit simulator an intra-bar range so SL-vs-target ties can be detected.
No tick rounding, no slippage, no brokerage (approximate MARKET fill at the signal-bar close premium).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd
from scipy.stats import norm

MIN_PER_YEAR = 365.0 * 24 * 60
IST = "Asia/Kolkata"


# ------------------------------------------------------------------ Black-Scholes
def bs_price(S, K, T, r, sigma, is_call: bool):
    """European Black-Scholes, no dividends. Vectorised over S and T."""
    S, T = np.asarray(S, dtype=float), np.asarray(T, dtype=float)
    sq = sigma * np.sqrt(T)
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / sq
    d2 = d1 - sq
    if is_call:
        return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def bs_delta(S, K, T, r, sigma, is_call: bool):
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    return norm.cdf(d1) if is_call else norm.cdf(d1) - 1.0


# ------------------------------------------------------------------ contract helpers
def expiry_datetime(day: date, index: str, cfg: dict) -> pd.Timestamp:
    """Nearest weekly expiry on/after `day`, at 15:30 IST. Uses the resolved list in cfg['synth']['expiry_dates'] (holiday shifts, see expiries.py)
    when attached; otherwise falls back to the plain weekday rule."""
    resolved = (cfg["synth"].get("expiry_dates") or {}).get(index)
    if resolved:
        nxt = [e for e in resolved if e >= day]
        if not nxt:
            raise ValueError(f"no resolved {index} expiry on/after {day}")
        d = nxt[0]
    else:
        wd = cfg["synth"]["expiry_weekday"][index]
        d = day + timedelta(days=(wd - day.weekday()) % 7)
    return pd.Timestamp(f"{d:%Y-%m-%d} {cfg['data']['market_close']}", tz=IST)


def strike_for(spot: float, side: int, index: str, cfg: dict) -> float:
    """ATM strike (nearest step), optionally N steps ITM (CE: lower strike, PE: higher strike)."""
    step = cfg["synth"]["strike_step"][index]
    atm = round(spot / step) * step
    return atm - side * cfg["synth"]["itm_steps"] * step


def years_to_expiry(now: pd.Series | pd.Timestamp, expiry: pd.Timestamp, cfg: dict):
    """Calendar time to expiry in years, floored at synth.min_T_minutes (guards expiry-day T -> 0)."""
    mins = (expiry - now) / pd.Timedelta(minutes=1)
    return np.maximum(np.asarray(mins, dtype=float), cfg["synth"]["min_T_minutes"]) / MIN_PER_YEAR


@dataclass(frozen=True)
class Contract:
    index: str
    side: int          # +1 CE, -1 PE
    strike: float
    expiry: pd.Timestamp
    mode: str          # "synth" | "real"

    @property
    def label(self) -> str:
        return f"{self.index} {self.expiry:%d%b%y} {self.strike:.0f} {'CE' if self.side > 0 else 'PE'}"


def synth_path(feat: pd.DataFrame, i0: int, side: int, index: str, cfg: dict):
    """Contract fixed at the entry bar (row i0); premium path (close/high/low per bar) from i0 onward.
    Returns (Contract, DataFrame[ts, ts_close, p_close, p_high, p_low])."""
    s = cfg["synth"]
    row = feat.iloc[i0]
    expiry = expiry_datetime(row["ts"].date(), index, cfg)
    K = strike_for(float(row["close"]), side, index, cfg)
    if s.get("dynamic_itm", False):
        # research doc Section 6: if the ATM premium is below the C8 sanity band, step ONE strike ITM; never step OTM.
        lo = cfg["gate"]["premium_band"][index][0]
        T0 = float(years_to_expiry(row["ts_close"], expiry, cfg))
        p_atm = float(bs_price(float(row["close"]), K, T0, s["risk_free"], s["iv"][index], side > 0))
        if p_atm < lo:
            K = K - side * s["strike_step"][index]
    c = Contract(index, side, K, expiry, "synth")
    f = feat.iloc[i0:]
    T = years_to_expiry(f["ts_close"], expiry, cfg)          # time at each bar's END
    is_call, iv, r = side > 0, s["iv"][index], s["risk_free"]
    p_close = bs_price(f["close"].to_numpy(), K, T, r, iv, is_call)
    p_hi_spot = bs_price(f["high"].to_numpy(), K, T, r, iv, is_call)
    p_lo_spot = bs_price(f["low"].to_numpy(), K, T, r, iv, is_call)
    hi, lo = (p_hi_spot, p_lo_spot) if is_call else (p_lo_spot, p_hi_spot)
    out = pd.DataFrame({"ts": f["ts"].to_numpy(), "ts_close": f["ts_close"].to_numpy(),
                        "p_close": p_close, "p_high": np.maximum.reduce([hi, lo, p_close]),
                        "p_low": np.minimum.reduce([hi, lo, p_close])})
    out["ts"] = pd.to_datetime(out["ts"]).dt.tz_convert(IST) if out["ts"].dt.tz is not None else out["ts"]
    return c, out.reset_index(drop=True)


# ------------------------------------------------------------------ REAL mode
class RealPremiumUnavailable(RuntimeError):
    pass


def real_path(*args, **kwargs):
    """REAL mode (Dhan expired/rolling options). Filled in once the endpoint is confirmed from the docs."""
    raise RealPremiumUnavailable("real mode not implemented yet")


def get_path(feat, i0, side, index, cfg):
    """Dispatch on cfg['mode']; REAL failure falls back to SYNTH with a LOUD warning."""
    if cfg["mode"] == "real":
        try:
            return real_path(feat, i0, side, index, cfg)
        except Exception as e:
            print(f"!!! WARNING: REAL premium unavailable ({e}); FALLING BACK TO SYNTH for this signal !!!")
    return synth_path(feat, i0, side, index, cfg)
