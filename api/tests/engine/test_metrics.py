"""T5 tests: SimState fill accounting, PnL, inventory, summary builder."""

from __future__ import annotations

from engine.datamodel.types import Fill
from engine.metrics.inventory import inventory_stats
from engine.metrics.pnl import realized_and_mark
from engine.metrics.summary import RunSummary, build_summary
from engine.simulator.state import SimState


def _fill(symbol: str, price: int, quantity: int, ts: int = 0) -> Fill:
    return Fill(symbol=symbol, price=price, quantity=quantity, source="book", timestamp=ts)


class TestSimStateFillAccounting:
    def test_buy_then_sell_realizes_profit(self) -> None:
        s = SimState()
        s.apply_fill(_fill("KELP", 100, 10))
        s.apply_fill(_fill("KELP", 110, -10))
        assert s.positions["KELP"] == 0
        assert s.cash == -100 * 10 + 110 * 10  # 100
        assert s.realized_pnl_by_product["KELP"] == 100.0

    def test_open_position_mark_to_market(self) -> None:
        s = SimState()
        s.apply_fill(_fill("KELP", 100, 10))
        assert s.positions["KELP"] == 10
        mark = s.mark_to_market({"KELP": 105.0})
        assert mark == 50.0  # (105 - 100) * 10

    def test_sell_short_then_buy_back_realizes(self) -> None:
        s = SimState()
        s.apply_fill(_fill("KELP", 110, -10))
        s.apply_fill(_fill("KELP", 100, 10))
        assert s.positions["KELP"] == 0
        assert s.realized_pnl_by_product["KELP"] == 100.0

    def test_vwap_cost_averages_multiple_buys(self) -> None:
        s = SimState()
        s.apply_fill(_fill("KELP", 100, 5))
        s.apply_fill(_fill("KELP", 110, 5))
        assert s.vwap_cost["KELP"] == 105.0

    def test_partial_reduce_leaves_vwap(self) -> None:
        s = SimState()
        s.apply_fill(_fill("KELP", 100, 10))
        s.apply_fill(_fill("KELP", 105, -5))
        assert s.positions["KELP"] == 5
        assert s.vwap_cost["KELP"] == 100.0
        assert s.realized_pnl_by_product["KELP"] == 25.0

    def test_flip_through_zero(self) -> None:
        s = SimState()
        s.apply_fill(_fill("KELP", 100, 5))
        s.apply_fill(_fill("KELP", 110, -15))  # close 5 @ profit 50, open short 10 at 110
        assert s.positions["KELP"] == -10
        assert s.realized_pnl_by_product["KELP"] == 50.0
        assert s.vwap_cost["KELP"] == 110.0


class TestPnlSnapshot:
    def test_snapshot_reflects_cash_and_mark(self) -> None:
        s = SimState()
        s.apply_fill(_fill("KELP", 100, 10))
        snap = realized_and_mark(s, mid_prices={"KELP": 105.0})
        assert snap.cash == -1000
        assert snap.mark == 50.0  # unrealized


class TestInventoryStats:
    def test_empty_history(self) -> None:
        stats = inventory_stats([], [])
        assert stats.max_abs_position == 0
        assert stats.turnover == 0

    def test_max_abs_and_turnover(self) -> None:
        history = [0, 10, 5, -3, 0]
        fills = [10, -5, -8, 3]
        stats = inventory_stats(history, fills)
        assert stats.max_abs_position == 10
        assert stats.turnover == 26
        assert stats.avg_abs_position == pytest_approx(3.6)


class TestRunSummaryBuilder:
    def test_build_summary_returns_validated_model(self) -> None:
        summary = build_summary(
            run_id="r1",
            strategy_path="noop.py",
            strategy_hash="sha256:abc",
            round_num=0,
            day=-2,
            matcher="depth_only",
            params={},
            engine_version="0.1.0",
            duration_ms=1234,
            pnl_total=123.45,
            pnl_by_product={"KELP": 123.45},
            max_inventory_by_product={"KELP": 10},
            turnover_by_product={"KELP": 50},
            num_events=20000,
            artifact_dir="storage/runs/r1",
        )
        assert isinstance(summary, RunSummary)
        assert summary.run_id == "r1"
        assert summary.pnl_total == 123.45
        # alias round-trip
        dumped = summary.model_dump(by_alias=True)
        assert dumped["_id"] == "r1"


def pytest_approx(value: float, tol: float = 1e-9):
    """Tiny shim to avoid importing pytest.approx here."""

    class _Approx:
        def __eq__(self, other: object) -> bool:
            return isinstance(other, (int, float)) and abs(other - value) < tol

    return _Approx()
