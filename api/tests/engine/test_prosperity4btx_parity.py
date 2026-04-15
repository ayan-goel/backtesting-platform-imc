"""Parity oracle: our `simulate_day` must agree with `prosperity4btx` on fills and P&L.

This is the regression gate for the IMC-matcher port. If this test ever fails, the
port has drifted away from the community reference. The test runs `prosperity4btx`
as a subprocess and compares the final `profit_and_loss` column of its activity log
against our `simulate_day` result on the same strategy + day.

Skipped if `prosperity4btx` is not installed or Round 1 data is not reachable.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from engine.config.rounds import resolve_limits
from engine.market.loader import load_round_day
from engine.matching.factory import resolve_matcher
from engine.simulator.runner import RunConfig, simulate_day
from engine.simulator.strategy_loader import hash_strategy_file, load_trader

# Repo-relative paths. Parents[4] from this test file lands at the repo root
# (imc-prosperity-4/), one level above platform/.
REPO_ROOT = Path(__file__).resolve().parents[4]
STRATEGY_PATH = REPO_ROOT / "strategies" / "uploaded" / "120866" / "120866.py"
ROUND1_DATA = REPO_ROOT.parent / "ROUND1"  # sibling of imc-prosperity-4/

DAYS = [0, -1, -2]


def _p4btx_available() -> bool:
    if shutil.which("prosperity4btx") is None:
        return False
    try:
        import prosperity4bt  # noqa: F401
    except ImportError:
        return False
    return True


def _p4btx_pkg_dir() -> Path:
    """Return the prosperity4bt package directory so we can put it on PYTHONPATH.

    The bundled `datamodel.py` lives here; strategies import `from datamodel import …`
    and prosperity4btx's `parse_algorithm` doesn't inject any shim, so we rely on
    it being importable from sys.path.
    """
    import prosperity4bt

    return Path(next(iter(prosperity4bt.__path__)))


pytestmark = [
    pytest.mark.skipif(not STRATEGY_PATH.is_file(), reason="uploaded strategy 120866 missing"),
    pytest.mark.skipif(not ROUND1_DATA.is_dir(), reason=f"ROUND1 data dir not found at {ROUND1_DATA}"),
    pytest.mark.skipif(not _p4btx_available(), reason="prosperity4btx not installed"),
]


def _run_ours(day: int) -> dict[str, float]:
    """Return {product: final_pnl} from our simulator for Round 1, given day."""
    trader = load_trader(STRATEGY_PATH)
    md = load_round_day(round_num=1, day=day, data_root=ROUND1_DATA)
    limits = resolve_limits(round_num=1, products=md.products, default_limit=50)
    config = RunConfig(
        run_id=f"parity-r1d{day}",
        strategy_path=str(STRATEGY_PATH),
        strategy_hash=hash_strategy_file(STRATEGY_PATH),
        round=1,
        day=day,
        matcher_name="imc",
        position_limits=limits,
        output_dir=Path("/tmp/parity-runs") / f"ours-r1d{day}",
    )
    result = simulate_day(
        trader=trader,
        market_data=md,
        matcher=resolve_matcher("imc", "all"),
        config=config,
    )
    return dict(result.summary.pnl_by_product)


def _run_p4btx(day: int, tmp_path: Path) -> dict[str, float]:
    """Return {product: final_pnl} from prosperity4btx for Round 1, given day."""
    # prosperity4btx expects <data_root>/round<N>/prices_round_N_day_M.csv — set it up.
    data_dir = tmp_path / "p4btx-data"
    (data_dir / "round1").mkdir(parents=True, exist_ok=True)
    for name in ROUND1_DATA.iterdir():
        if name.suffix == ".csv":
            shutil.copy(name, data_dir / "round1" / name.name)

    log_file = tmp_path / f"p4btx-r1d{day}.log"
    env = os.environ.copy()
    pkg_dir = str(_p4btx_pkg_dir())
    env["PYTHONPATH"] = pkg_dir + os.pathsep + env.get("PYTHONPATH", "")

    proc = subprocess.run(
        [
            "prosperity4btx",
            str(STRATEGY_PATH),
            f"1-{day}",
            "--data",
            str(data_dir),
            "--out",
            str(log_file),
            "--no-progress",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert proc.returncode == 0, f"prosperity4btx failed:\n{proc.stdout}\n{proc.stderr}"
    assert log_file.is_file(), f"log not written to {log_file}"

    # Parse the activity log (second section, semicolon-delimited CSV) and grab the
    # final profit_and_loss for each product.
    content = log_file.read_text(encoding="utf-8").splitlines()
    try:
        hdr_idx = next(i for i, line in enumerate(content) if line == "Activities log:")
    except StopIteration as e:
        raise AssertionError("activity log section not found") from e

    final_pnl: dict[str, float] = {}
    for line in content[hdr_idx + 2 :]:
        if not line or ";" not in line:
            break  # end of CSV section
        parts = line.split(";")
        if len(parts) < 17:
            break
        product = parts[2]
        try:
            pnl = float(parts[-1])
        except ValueError:
            continue
        final_pnl[product] = pnl  # overwritten each row → last one wins
    return final_pnl


@pytest.mark.parametrize("day", DAYS)
def test_parity_120866_round1(day: int, tmp_path: Path) -> None:
    """Our backtester's P&L for strategy 120866 must match prosperity4btx exactly."""
    ours = _run_ours(day)
    theirs = _run_p4btx(day, tmp_path)

    # Both should have the same products
    assert set(ours) == set(theirs), f"product mismatch: ours={set(ours)} theirs={set(theirs)}"

    # Compare each product to the cent
    for product in ours:
        assert ours[product] == pytest.approx(theirs[product], abs=0.01), (
            f"day {day} {product}: ours={ours[product]:.2f} theirs={theirs[product]:.2f}"
        )
