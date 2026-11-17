"""Shared helpers for the signals reverse-engineering study (read-only; reuses backtest/dhan_client)."""
from __future__ import annotations
import sys
from pathlib import Path
import pandas as pd

BT = Path(__file__).resolve().parents[2]          # .../backtest
sys.path.insert(0, str(BT))
from dhan_client import DhanClient, load_config, TokenExpiredError  # noqa: E402
from candles import load_scrip_master, resolve_index_id             # noqa: E402

IST = "Asia/Kolkata"
CACHE = BT / "data" / "cache" / "signals"            # data/cache/ is git-ignored
CACHE.mkdir(parents=True, exist_ok=True)
SIGNALS_XLSX = BT.parent / "signals" / "signals.xlsx"
OUT = Path(__file__).resolve().parent / "out"
OUT.mkdir(exist_ok=True)
