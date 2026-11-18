"""Mutation self-check (M3 acceptance): six deliberate off-by-one bugs are injected into a COPY of gate.py; the gate test-suite
must fail for each of them. If a mutant survives, the suite is too weak."""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

MUTANTS = {
    "C7 uses >= (-7000 would pass)": ("return day_realised_pnl > day_brake", "return day_realised_pnl >= day_brake"),
    "C5 end inclusive (13:00:00 blocked)": ("return not (start <= t < end)", "return not (start <= t <= end)"),
    "C5 start exclusive (12:00:00 allowed)": ("return not (start <= t < end)", "return not (start < t < end)"),
    "C2 uses <= (exactly th_exh passes)": ("sm30 < th_exh", "sm30 <= th_exh"),
    "C4 inclusive bounds": ("rng_min < rng < rng_max", "rng_min <= rng <= rng_max"),
    "timeout is 59 min": ('pd.Timedelta(minutes=g["timeout_minutes"])', 'pd.Timedelta(minutes=g["timeout_minutes"] - 1)'),
}


def _copy_project(dst: Path) -> None:
    ignore = shutil.ignore_patterns("data", "__pycache__", ".pytest_cache", "results", ".env", "*.csv")
    shutil.copytree(ROOT, dst, ignore=ignore)


def test_baseline_suite_passes_on_unmutated_copy():
    with tempfile.TemporaryDirectory() as td:
        dst = Path(td) / "p"
        _copy_project(dst)
        r = subprocess.run([sys.executable, "-m", "pytest", "tests/test_gate.py", "-q", "-x", "-p", "no:cacheprovider"],
                           cwd=dst, capture_output=True, text=True, env={**os.environ, "BACKTEST_VERSION": os.environ.get("BACKTEST_VERSION", "v3")})
        assert r.returncode == 0, r.stdout[-800:]


@pytest.mark.parametrize("name", list(MUTANTS))
def test_mutant_is_killed(name):
    old, new = MUTANTS[name]
    with tempfile.TemporaryDirectory() as td:
        dst = Path(td) / "p"
        _copy_project(dst)
        src = (dst / "gate.py").read_text(encoding="utf-8")
        assert old in src, f"mutation target not found in gate.py: {old!r}"
        (dst / "gate.py").write_text(src.replace(old, new), encoding="utf-8")
        r = subprocess.run([sys.executable, "-m", "pytest", "tests/test_gate.py", "-q", "-x", "-p", "no:cacheprovider"],
                           cwd=dst, capture_output=True, text=True, env={**os.environ, "BACKTEST_VERSION": os.environ.get("BACKTEST_VERSION", "v3")})
        assert r.returncode != 0, f"MUTANT SURVIVED: {name}\n{r.stdout[-600:]}"
