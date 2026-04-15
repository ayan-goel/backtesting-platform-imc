"""Block-bootstrap generator tests."""

from __future__ import annotations

import numpy as np

from engine.montecarlo.builder import build_synthetic_market_data
from engine.montecarlo.generators.block_bootstrap import BlockBootstrapGenerator
from engine.montecarlo.rng import rng_for_path

from tests.engine._mc_fixtures import make_synthetic_market_data


def test_degenerate_block_size_equals_length_reproduces_historical() -> None:
    md = make_synthetic_market_data(num_timestamps=50)
    gen = BlockBootstrapGenerator()
    rng = rng_for_path(run_seed=0, path_index=0)
    out = build_synthetic_market_data(
        historical=md,
        generator=gen,
        calibration=None,
        params={"block_size": len(md.timestamps)},
        rng=rng,
    )
    # block_size == len and max_start == 0 so the only start is 0 → identity.
    for ts in md.timestamps:
        assert out.frames[ts] == md.frames[ts]


def test_determinism_same_seed_same_output() -> None:
    md = make_synthetic_market_data(num_timestamps=80)
    gen = BlockBootstrapGenerator()
    a = build_synthetic_market_data(
        historical=md,
        generator=gen,
        calibration=None,
        params={"block_size": 10},
        rng=rng_for_path(run_seed=42, path_index=0),
    )
    b = build_synthetic_market_data(
        historical=md,
        generator=gen,
        calibration=None,
        params={"block_size": 10},
        rng=rng_for_path(run_seed=42, path_index=0),
    )
    for ts in md.timestamps:
        assert a.frames[ts] == b.frames[ts]


def test_different_seeds_produce_different_paths() -> None:
    md = make_synthetic_market_data(num_timestamps=80)
    gen = BlockBootstrapGenerator()
    a = build_synthetic_market_data(
        historical=md,
        generator=gen,
        calibration=None,
        params={"block_size": 10},
        rng=rng_for_path(run_seed=42, path_index=0),
    )
    b = build_synthetic_market_data(
        historical=md,
        generator=gen,
        calibration=None,
        params={"block_size": 10},
        rng=rng_for_path(run_seed=42, path_index=1),
    )
    any_diff = any(a.frames[ts] != b.frames[ts] for ts in md.timestamps)
    assert any_diff


def test_every_frame_is_a_historical_frame() -> None:
    md = make_synthetic_market_data(num_timestamps=80)
    historical_frames = set()
    for frame in md.frames.values():
        historical_frames.add(_hash_frame(frame))
    gen = BlockBootstrapGenerator()
    out = build_synthetic_market_data(
        historical=md,
        generator=gen,
        calibration=None,
        params={"block_size": 7},
        rng=rng_for_path(run_seed=123, path_index=0),
    )
    for frame in out.frames.values():
        assert _hash_frame(frame) in historical_frames


def test_block_size_one_behaves_as_iid_resample() -> None:
    md = make_synthetic_market_data(num_timestamps=200)
    gen = BlockBootstrapGenerator()
    out = build_synthetic_market_data(
        historical=md,
        generator=gen,
        calibration=None,
        params={"block_size": 1},
        rng=rng_for_path(run_seed=7, path_index=0),
    )
    # Expect roughly uniform coverage of historical indices — chi-square at 1% tol.
    counts: dict[tuple, int] = {}
    for frame in out.frames.values():
        key = _hash_frame(frame)
        counts[key] = counts.get(key, 0) + 1
    observed = np.asarray(list(counts.values()), dtype=np.float64)
    expected = np.full_like(observed, fill_value=observed.sum() / observed.size)
    chi2 = float(np.sum((observed - expected) ** 2 / expected))
    # Fairly loose: 200 draws into up to 200 bins is high variance. We just
    # assert we got something close to uniform — not a tight goodness-of-fit.
    assert chi2 < 5 * observed.size


def test_spine_is_preserved() -> None:
    md = make_synthetic_market_data(num_timestamps=60)
    out = build_synthetic_market_data(
        historical=md,
        generator=BlockBootstrapGenerator(),
        calibration=None,
        params={"block_size": 10},
        rng=rng_for_path(run_seed=1, path_index=0),
    )
    assert out.timestamps == md.timestamps
    assert out.products == md.products
    assert out.round == md.round and out.day == md.day


def _hash_frame(frame: dict) -> tuple:
    parts = []
    for product in sorted(frame):
        snap = frame[product]
        parts.append(
            (
                product,
                tuple(sorted(snap.order_depth.buy_orders.items())),
                tuple(sorted(snap.order_depth.sell_orders.items())),
                tuple(
                    (t.price, t.quantity, t.timestamp) for t in snap.market_trades
                ),
            )
        )
    return tuple(parts)
