"""Block-bootstrap generator.

Resamples historical frames in contiguous blocks of length `block_size`.
Every synthetic frame is an unmodified historical frame, so matcher
invariants (spread > 0, depth shape, market-trade integer prices) are
preserved by construction — the only thing that changes is the *order*
in which frames are presented to the strategy.

Block length controls the horizon over which auto-correlation is
preserved. `block_size=len(timestamps)` → the output is a permutation
(length 1) of the input and the first-block-start-0 seed anchors to
historical. `block_size=1` → i.i.d. resampling of frames.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import numpy as np

from engine.market.loader import MarketData, ProductSnap


@dataclass(frozen=True, slots=True)
class BlockBootstrapGenerator:
    name: str = "block_bootstrap"
    default_block_size: int = 50

    def generate(
        self,
        *,
        historical: MarketData,
        calibration: Any | None = None,  # noqa: ARG002
        params: Mapping[str, Any] | None = None,
        rng: np.random.Generator,
    ) -> MarketData:
        block_size = int((params or {}).get("block_size", self.default_block_size))
        n = len(historical.timestamps)
        if block_size < 1:
            raise ValueError(f"block_size must be >= 1, got {block_size}")
        block_size = min(block_size, n)

        max_start = n - block_size
        num_blocks = (n + block_size - 1) // block_size

        if max_start == 0:
            starts = np.zeros(num_blocks, dtype=np.int64)
        else:
            starts = rng.integers(
                low=0, high=max_start + 1, size=num_blocks, dtype=np.int64
            )

        indices: list[int] = []
        for start in starts:
            indices.extend(range(int(start), int(start) + block_size))
            if len(indices) >= n:
                break
        indices = indices[:n]

        new_frames: dict[int, dict[str, ProductSnap]] = {}
        for new_idx, src_idx in enumerate(indices):
            target_ts = historical.timestamps[new_idx]
            src_ts = historical.timestamps[src_idx]
            src_frame = historical.frames[src_ts]
            # Copy the frame dict so we don't accidentally mutate history, but
            # keep the ProductSnap instances themselves — they're frozen.
            new_frames[target_ts] = dict(src_frame)

        return MarketData(
            round=historical.round,
            day=historical.day,
            timestamps=historical.timestamps,
            products=historical.products,
            frames=new_frames,
        )
