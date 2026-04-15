"""Local grid search — no server required.

Builds the Cartesian product of a `--space` JSON file, runs each trial in a
ProcessPoolExecutor worker (fresh Python process per trial → clean sys.modules),
and writes ranked results to `storage/gridsearch/<run_id>/results.jsonl`.

Usage:
    prosperity gridsearch -s strategy.py -r 1 -d 0 \\
        --data-root ROUND1/ --space ./space.json --workers 4

`space.json` format:
    {
        "PARAM_A": [1, 2, 3],
        "PARAM_B": [0.1, 0.2]
    }

The strategy reads `self.params["PARAM_A"]` etc. — `simulate_day` injects the
trial's `params` dict into `trader.params` before calling `trader.run`.
"""

from __future__ import annotations

import itertools
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from engine.config.rounds import resolve_limits
from engine.errors import ProsperityError
from engine.market.loader import load_round_day
from engine.matching.factory import DEFAULT_MATCHER, DEFAULT_MODE, resolve_matcher
from engine.simulator.runner import RunConfig, simulate_day
from engine.simulator.strategy_loader import hash_strategy_file, load_trader


def register(app: typer.Typer) -> None:
    """Attach the gridsearch command to an existing Typer app."""
    app.command("gridsearch")(gridsearch)


def gridsearch(
    strategy: Path = typer.Option(..., "--strategy", "-s", help="Path to a strategy file."),
    round_num: int = typer.Option(..., "--round", "-r", help="Round number."),
    day: int = typer.Option(..., "--day", "-d", help="Day number."),
    space: Path = typer.Option(..., "--space", help="JSON file with {param: [values...]}."),
    data_root: Path = typer.Option(
        Path("storage/data"),
        "--data-root",
        help="Directory holding prices_round_N_day_M.csv and trades_*.csv.",
    ),
    matcher: str = typer.Option(DEFAULT_MATCHER, "--matcher", help="Matcher name."),
    match_mode: str = typer.Option(
        DEFAULT_MODE.value,
        "--match-mode",
        help="Trade-matching mode (all/worse/none) for the imc matcher.",
    ),
    position_limit: int = typer.Option(
        50,
        "--limit",
        help="Fallback per-product limit for products not listed in rounds.json.",
    ),
    workers: int = typer.Option(
        0, "--workers", "-w", help="Parallel worker count. 0 = os.cpu_count()."
    ),
    objective: str = typer.Option(
        "pnl_total",
        "--objective",
        help="Trial ranking key: pnl_total or pnl_by_product.<SYMBOL>.",
    ),
    direction: str = typer.Option("maximize", "--direction"),
    top: int = typer.Option(10, "--top", help="Rows to display in the summary table."),
    out: Path = typer.Option(
        Path("platform/storage/gridsearch"),
        "--out",
        help="Directory where gridsearch artifacts are written.",
    ),
) -> None:
    """Run a local grid search without touching the FastAPI server."""
    console = Console()

    if direction not in ("maximize", "minimize"):
        raise typer.BadParameter("--direction must be 'maximize' or 'minimize'")
    if not space.is_file():
        raise typer.BadParameter(f"space file not found: {space}")
    space_raw = json.loads(space.read_text(encoding="utf-8"))
    if not isinstance(space_raw, dict) or not space_raw:
        raise typer.BadParameter("space must be a non-empty object {param: [values]}")
    for k, v in space_raw.items():
        if not isinstance(v, list) or not v:
            raise typer.BadParameter(f"space[{k!r}] must be a non-empty list")

    trials = _cartesian(space_raw)
    total = len(trials)
    console.print(f"[bold]gridsearch[/bold]: {total} trials across {len(space_raw)} params")

    strategy = strategy.resolve()
    data_root = data_root.resolve()

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + f"__{strategy.stem}__gs"
    run_dir = (out / run_id).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    results_path = run_dir / "results.jsonl"
    space_snapshot = run_dir / "space.json"
    space_snapshot.write_text(json.dumps(space_raw, indent=2), encoding="utf-8")

    shared: dict[str, Any] = {
        "strategy_path": str(strategy),
        "round_num": round_num,
        "day": day,
        "data_root": str(data_root),
        "matcher": matcher,
        "match_mode": match_mode,
        "position_limit": position_limit,
        "output_root": str(run_dir / "trials"),
    }

    max_workers = workers if workers > 0 else None
    start = time.monotonic()
    results: list[dict[str, Any]] = []
    with results_path.open("w", encoding="utf-8") as log, Progress(
        SpinnerColumn(),
        TextColumn("{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task(f"running {total} trials", total=total)
        with ProcessPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(_run_trial, shared, i, params): (i, params)
                for i, params in enumerate(trials)
            }
            for fut in as_completed(futures):
                i, params = futures[fut]
                try:
                    row = fut.result()
                except Exception as e:
                    row = {
                        "trial": i,
                        "params": params,
                        "status": "failed",
                        "error": f"{type(e).__name__}: {e}",
                    }
                log.write(json.dumps(row) + "\n")
                log.flush()
                results.append(row)
                progress.advance(task)

    duration_s = time.monotonic() - start
    console.print(
        f"[green]done[/green]: {total} trials in {duration_s:.1f}s "
        f"-> {results_path}"
    )

    ranked = _rank(results, objective, direction)
    _print_top(console, ranked, objective, top)


def _cartesian(space: dict[str, list[Any]]) -> list[dict[str, Any]]:
    keys = list(space.keys())
    value_lists = [space[k] for k in keys]
    return [dict(zip(keys, combo, strict=True)) for combo in itertools.product(*value_lists)]


def _rank(
    results: list[dict[str, Any]], objective: str, direction: str
) -> list[dict[str, Any]]:
    succeeded = [r for r in results if r.get("status") == "succeeded"]
    reverse = direction == "maximize"

    def key(row: dict[str, Any]) -> float:
        val = _extract_objective(row, objective)
        return float("-inf") if val is None else float(val)

    return sorted(succeeded, key=key, reverse=reverse)


def _extract_objective(row: dict[str, Any], objective: str) -> float | None:
    if "." in objective:
        head, tail = objective.split(".", 1)
        inner = row.get(head) or {}
        if isinstance(inner, dict):
            return inner.get(tail)
        return None
    return row.get(objective)


def _print_top(
    console: Console, ranked: list[dict[str, Any]], objective: str, top: int
) -> None:
    if not ranked:
        console.print("[yellow]no succeeded trials[/yellow]")
        return
    param_keys = sorted(ranked[0].get("params", {}).keys())
    table = Table(title=f"top {min(top, len(ranked))} trials by {objective}")
    table.add_column("rank", justify="right")
    table.add_column("trial", justify="right")
    table.add_column("value", justify="right")
    for k in param_keys:
        table.add_column(k)
    for rank, row in enumerate(ranked[:top], start=1):
        val = _extract_objective(row, objective)
        table.add_row(
            str(rank),
            str(row.get("trial")),
            f"{val:.2f}" if isinstance(val, (int, float)) else "—",
            *[str(row.get("params", {}).get(k, "")) for k in param_keys],
        )
    console.print(table)


def _run_trial(shared: dict[str, Any], trial_idx: int, params: dict[str, Any]) -> dict[str, Any]:
    """Run one backtest in a worker process. Must be picklable → module-level fn."""
    try:
        strategy_path = Path(shared["strategy_path"])
        trader = load_trader(strategy_path)
        md = load_round_day(
            shared["round_num"], shared["day"], Path(shared["data_root"])
        )
        limits = resolve_limits(shared["round_num"], md.products, shared["position_limit"])
        matcher = resolve_matcher(shared["matcher"], shared["match_mode"])
        output_dir = Path(shared["output_root"]) / f"trial_{trial_idx:05d}"
        config = RunConfig(
            run_id=f"gs_trial_{trial_idx}",
            strategy_path=str(strategy_path),
            strategy_hash=hash_strategy_file(strategy_path),
            round=shared["round_num"],
            day=shared["day"],
            matcher_name=shared["matcher"],
            position_limits=limits,
            output_dir=output_dir,
            params=params,
        )
        start = time.monotonic()
        result = simulate_day(trader=trader, market_data=md, matcher=matcher, config=config)
        duration_ms = int((time.monotonic() - start) * 1000)
        summary = result.summary.model_dump(by_alias=True)
        return {
            "trial": trial_idx,
            "params": params,
            "status": "succeeded",
            "pnl_total": summary.get("pnl_total"),
            "pnl_by_product": summary.get("pnl_by_product", {}),
            "duration_ms": duration_ms,
            "run_id": config.run_id,
        }
    except ProsperityError as e:
        return {
            "trial": trial_idx,
            "params": params,
            "status": "failed",
            "error": f"{type(e).__name__}: {e}",
        }
