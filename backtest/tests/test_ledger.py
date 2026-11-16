import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from ledger import LEDGER_COLUMNS, make_row, write_ledger

SPEC = ["date", "time", "index", "contract", "side", "entry", "lot", "exit", "exit_reason", "pnl", "sm5", "sm30",
        "rng", "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "verdict", "skip_reason", "mode"]


def test_columns_match_spec_exactly():
    assert LEDGER_COLUMNS == SPEC


def test_make_row_rejects_unknown_columns_and_blank_fills():
    with pytest.raises(KeyError):
        make_row(foo=1)
    assert list(make_row(date="2025-10-06")) == SPEC


def test_write_ledger_roundtrip(tmp_path):
    p = tmp_path / "l.csv"
    write_ledger([make_row(date="2025-10-06", verdict="SKIP", skip_reason="C5")], p)
    assert p.read_text().splitlines()[0].split(",") == SPEC
