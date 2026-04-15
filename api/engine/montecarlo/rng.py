"""Deterministic RNG seeding for Monte Carlo paths.

Every synthetic path in an MC simulation is fully determined by
`(run_seed, path_index)`. Two paths from the same (seed, index) pair MUST
produce byte-identical output — that is the contract generators rely on
for reproducibility, and what lets the parallel worker pool verify itself
against the single-threaded path.
"""

from __future__ import annotations

import numpy as np


def rng_for_path(run_seed: int, path_index: int) -> np.random.Generator:
    """Return an independent PCG64 generator keyed by `(run_seed, path_index)`.

    Uses `SeedSequence.spawn` so paths share no mutable state and can be
    advanced in parallel without cross-talk. The returned `Generator`
    instance is safe to consume inside a single process.
    """
    if path_index < 0:
        raise ValueError(f"path_index must be non-negative, got {path_index}")
    seed_seq = np.random.SeedSequence(entropy=run_seed, spawn_key=(path_index,))
    return np.random.Generator(np.random.PCG64(seed_seq))
