"""Trade/skip ledger (CSV). One row per candidate signal, taken or skipped.
Column names are fixed by the spec (matches the Excel tracker schema)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

LEDGER_COLUMNS = [
    "date", "time", "index", "contract", "side", "entry", "lot", "exit", "exit_reason", "pnl",
    "sm5", "sm30", "rng", "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8",
    "verdict", "skip_reason", "mode",
]


def make_row(**kw) -> dict:
    """Build a ledger row; missing columns become empty, unknown columns are rejected."""
    extra = set(kw) - set(LEDGER_COLUMNS)
    if extra:
        raise KeyError(f"not ledger columns: {sorted(extra)}")
    return {c: kw.get(c, "") for c in LEDGER_COLUMNS}


def write_ledger(rows: list[dict], path: Path | str) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=LEDGER_COLUMNS)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)   # plain ASCII CSV: opens cleanly in Excel and pandas
    return df
