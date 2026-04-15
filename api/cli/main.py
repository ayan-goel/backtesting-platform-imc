"""Typer CLI: `prosperity run` (execute a backtest) + `prosperity inspect` (show a run)."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from importlib.metadata import version as pkg_version
from pathlib import Path
from typing import Any

import httpx
import typer
from rich.console import Console
from rich.table import Table

from cli import api_client
from cli.gridsearch import register as _register_gridsearch
from engine.config.rounds import resolve_limits
from engine.errors import ProsperityError
from engine.market.loader import load_round_day
from engine.matching.factory import DEFAULT_MATCHER, DEFAULT_MODE, resolve_matcher
from engine.simulator.runner import RunConfig, simulate_day
from engine.simulator.strategy_loader import hash_strategy_file, load_trader

app = typer.Typer(
    help="IMC Prosperity 4 backtesting platform CLI",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


_register_gridsearch(app)


@app.callback()
def _root() -> None:
    """Root callback. Present so Typer doesn't collapse a single-command app."""


@app.command()
def version() -> None:
    """Print the platform version."""
    typer.echo(pkg_version("prosperity-api"))


@app.command()
def run(
    strategy: Path = typer.Option(..., "--strategy", "-s", help="Path to a strategy file."),
    round_num: int = typer.Option(..., "--round", "-r", help="Round number."),
    day: int = typer.Option(..., "--day", "-d", help="Day number."),
    data_root: Path = typer.Option(
        Path("storage/data"),
        "--data-root",
        help="Directory holding prices_round_N_day_M.csv and trades_*.csv. "
        "Defaults to the uploaded-dataset store; pass a repo path for local dev.",
    ),
    matcher: str = typer.Option(
        DEFAULT_MATCHER,
        "--matcher",
        help="Matcher name: imc (default, parity with prosperity4btx), depth_only, depth_and_trades.",
    ),
    match_mode: str = typer.Option(
        DEFAULT_MODE.value,
        "--match-mode",
        help="Trade-matching mode for imc matcher: all, worse, none. Ignored by other matchers.",
    ),
    out: Path = typer.Option(
        Path("platform/storage/runs"),
        "--out",
        help="Directory where run artifacts are written.",
    ),
    position_limit: int = typer.Option(
        50,
        "--limit",
        help="Fallback per-product limit for products not listed in rounds.json.",
    ),
) -> None:
    """Run a backtest on one (round, day) and write artifacts under `out/<run_id>/`."""
    strategy = strategy.resolve()
    data_root = data_root.resolve()

    try:
        trader = load_trader(strategy)
        strat_hash = hash_strategy_file(strategy)
        md = load_round_day(round_num, day, data_root)

        run_id = _build_run_id(strategy, round_num, day)
        output_dir = (out / run_id).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        limits = resolve_limits(round_num, md.products, position_limit)

        config = RunConfig(
            run_id=run_id,
            strategy_path=str(strategy),
            strategy_hash=strat_hash,
            round=round_num,
            day=day,
            matcher_name=matcher,
            position_limits=limits,
            output_dir=output_dir,
        )

        matcher_impl = resolve_matcher(matcher, match_mode)
        result = simulate_day(
            trader=trader,
            market_data=md,
            matcher=matcher_impl,
            config=config,
        )

        config_path = output_dir / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "strategy_path": str(strategy),
                    "strategy_hash": strat_hash,
                    "round": round_num,
                    "day": day,
                    "matcher": matcher,
                    "position_limits": config.position_limits,
                    "engine_version": config.engine_version,
                },
                indent=2,
            )
        )

        _print_summary(result.summary.model_dump(by_alias=True))
    except ProsperityError as e:
        console.print(f"[red]engine error[/red]: {e}")
        raise typer.Exit(code=2) from e
    except FileNotFoundError as e:
        console.print(f"[red]file not found[/red]: {e}")
        raise typer.Exit(code=1) from e


@app.command()
def inspect(
    run_id: str = typer.Argument(..., help="Run id (directory name under storage/runs)."),
    storage_root: Path = typer.Option(
        Path("platform/storage/runs"),
        "--storage",
        help="Directory holding run artifacts.",
    ),
    tail: int = typer.Option(5, "--tail", help="Show the last N event-log lines."),
) -> None:
    """Print a summary of a completed run."""
    run_dir = (storage_root / run_id).resolve()
    if not run_dir.is_dir():
        console.print(f"[red]run not found[/red]: {run_dir}")
        raise typer.Exit(code=1)

    config_path = run_dir / "config.json"
    events_path = run_dir / "events.jsonl"

    if config_path.is_file():
        console.print("[bold]config.json:[/bold]")
        console.print_json(config_path.read_text())

    if events_path.is_file():
        console.print(f"\n[bold]last {tail} events:[/bold]")
        lines = events_path.read_text().splitlines()
        for line in lines[-tail:]:
            console.print_json(line)
        console.print(f"\ntotal events: {len(lines)}")


def _build_run_id(strategy: Path, round_num: int, day: int) -> str:
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{ts}__{strategy.stem}__r{round_num}d{day}"


def _print_summary(summary: dict[str, object]) -> None:
    table = Table(title="run summary", show_header=True, header_style="bold")
    table.add_column("field")
    table.add_column("value")
    for key in (
        "_id",
        "strategy_path",
        "round",
        "day",
        "matcher",
        "pnl_total",
        "duration_ms",
        "num_events",
        "status",
        "artifact_dir",
    ):
        table.add_row(key, str(summary.get(key, "")))
    console.print(table)

    by_product_raw = summary.get("pnl_by_product", {})
    if isinstance(by_product_raw, dict) and by_product_raw:
        p_table = Table(title="pnl by product", show_header=True)
        p_table.add_column("product")
        p_table.add_column("pnl")
        p_table.add_column("max_inv")
        p_table.add_column("turnover")
        max_inv_raw = summary.get("max_inventory_by_product", {}) or {}
        turnover_raw = summary.get("turnover_by_product", {}) or {}
        max_inv = max_inv_raw if isinstance(max_inv_raw, dict) else {}
        turnover = turnover_raw if isinstance(turnover_raw, dict) else {}
        for product, pnl in by_product_raw.items():
            p_table.add_row(
                str(product),
                f"{float(pnl):.2f}",
                str(max_inv.get(product, 0)),
                str(turnover.get(product, 0)),
            )
        console.print(p_table)


@app.command()
def batch(
    strategy: str = typer.Option(..., "--strategy", "-s", help="Uploaded strategy id."),
    datasets: str = typer.Option(
        "",
        "--datasets",
        help="Comma-separated (round:day) pairs, e.g. '0:-2,0:-1'.",
    ),
    matcher: str = typer.Option("depth_only", "--matcher"),
    position_limit: int = typer.Option(50, "--limit"),
    config: Path | None = typer.Option(
        None,
        "--config",
        help="Optional JSON file with {strategy_id, datasets: [{round, day}], matcher, position_limit, params}.",
    ),
    poll_seconds: float = typer.Option(2.0, "--poll", help="Poll interval in seconds."),
) -> None:
    """Submit a batch to POST /batches, poll until terminal, print leaderboard."""
    body = _build_batch_body(
        strategy_id=strategy,
        datasets=datasets,
        matcher=matcher,
        position_limit=position_limit,
        config_path=config,
    )
    try:
        client = api_client.build_client()
    except api_client.MissingApiKeyError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1) from e

    with client:
        try:
            post = client.post("/batches", json=body)
        except httpx.HTTPError as e:
            console.print(f"[red]POST /batches failed[/red]: {e}")
            raise typer.Exit(code=2) from e
        if post.status_code != 201:
            console.print(f"[red]POST /batches failed[/red]: {post.status_code} {post.text}")
            raise typer.Exit(code=2)
        doc = post.json()
        batch_id = doc["_id"]
        console.print(f"[green]submitted[/green]: {batch_id}")

        final = _poll_until_terminal(
            client,
            path=f"/batches/{batch_id}",
            terminal={"succeeded", "failed"},
            poll_seconds=poll_seconds,
        )

    _print_batch_leaderboard(final)
    if final.get("status") == "failed":
        raise typer.Exit(code=2)


def _build_batch_body(
    *,
    strategy_id: str,
    datasets: str,
    matcher: str,
    position_limit: int,
    config_path: Path | None,
) -> dict[str, Any]:
    """Merge CLI flags with an optional JSON config file. Flags trump file."""
    base: dict[str, Any] = {}
    if config_path is not None:
        base = json.loads(config_path.read_text())
    ds_list: list[dict[str, int]] = []
    if datasets:
        for token in datasets.split(","):
            token = token.strip()
            if not token:
                continue
            try:
                r_str, d_str = token.split(":")
                ds_list.append({"round": int(r_str), "day": int(d_str)})
            except ValueError as e:
                raise typer.BadParameter(
                    f"invalid datasets token {token!r}; expected 'round:day'"
                ) from e
    if not ds_list:
        ds_list = base.get("datasets", [])
    body: dict[str, Any] = {
        "strategy_id": strategy_id or base.get("strategy_id"),
        "datasets": ds_list,
        "matcher": matcher if matcher else base.get("matcher", "depth_only"),
        "position_limit": position_limit if position_limit else base.get("position_limit", 50),
        "params": base.get("params", {}),
    }
    if not body["strategy_id"]:
        raise typer.BadParameter("strategy_id is required")
    if not body["datasets"]:
        raise typer.BadParameter("at least one dataset is required")
    return body


def _poll_until_terminal(
    client: httpx.Client, *, path: str, terminal: set[str], poll_seconds: float
) -> dict[str, Any]:
    """Poll `path` until its `status` field lands in `terminal`."""
    while True:
        try:
            r = client.get(path)
        except httpx.HTTPError as e:
            console.print(f"[red]GET {path} failed[/red]: {e}")
            raise typer.Exit(code=2) from e
        if r.status_code != 200:
            console.print(f"[red]GET {path} failed[/red]: {r.status_code} {r.text}")
            raise typer.Exit(code=2)
        doc = r.json()
        status = doc.get("status")
        if status in terminal:
            return doc
        time.sleep(poll_seconds)


def _print_batch_leaderboard(batch_doc: dict[str, Any]) -> None:
    status = batch_doc.get("status", "?")
    progress = batch_doc.get("progress", {})
    console.print(
        f"[bold]status[/bold]: {status} "
        f"· {progress.get('completed', 0)}/{progress.get('total', 0)} succeeded"
    )
    tasks = list(batch_doc.get("tasks", []))
    tasks.sort(key=lambda t: t.get("pnl_total") or float("-inf"), reverse=True)
    table = Table(title="batch results", show_header=True)
    table.add_column("round/day")
    table.add_column("status")
    table.add_column("pnl", justify="right")
    table.add_column("duration", justify="right")
    table.add_column("error")
    for t in tasks:
        pnl = t.get("pnl_total")
        dur = t.get("duration_ms")
        table.add_row(
            f"r{t.get('round')}/d{t.get('day')}",
            str(t.get("status", "?")),
            f"{pnl:.2f}" if isinstance(pnl, (int, float)) else "—",
            f"{dur} ms" if isinstance(dur, int) else "—",
            (t.get("error") or "")[:60],
        )
    console.print(table)


@app.command()
def study(
    strategy: str = typer.Option(..., "--strategy", "-s", help="Uploaded strategy id."),
    round_num: int = typer.Option(..., "--round", "-r"),
    day: int = typer.Option(..., "--day", "-d"),
    space: Path = typer.Option(..., "--space", help="JSON file defining the search space."),
    n_trials: int = typer.Option(30, "--n-trials"),
    matcher: str = typer.Option("depth_only", "--matcher"),
    position_limit: int = typer.Option(50, "--limit"),
    objective: str = typer.Option("pnl_total", "--objective"),
    direction: str = typer.Option("maximize", "--direction"),
    poll_seconds: float = typer.Option(3.0, "--poll"),
) -> None:
    """Submit an optuna study via POST /studies, poll until terminal, print best trial."""
    if direction not in ("maximize", "minimize"):
        raise typer.BadParameter("--direction must be 'maximize' or 'minimize'")

    if not space.is_file():
        raise typer.BadParameter(f"space file not found: {space}")
    space_body = json.loads(space.read_text())

    body = {
        "strategy_id": strategy,
        "round": round_num,
        "day": day,
        "matcher": matcher,
        "position_limit": position_limit,
        "space": space_body,
        "objective": objective,
        "direction": direction,
        "n_trials": n_trials,
    }

    try:
        client = api_client.build_client(timeout=60.0)
    except api_client.MissingApiKeyError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1) from e

    with client:
        try:
            post = client.post("/studies", json=body)
        except httpx.HTTPError as e:
            console.print(f"[red]POST /studies failed[/red]: {e}")
            raise typer.Exit(code=2) from e
        if post.status_code != 201:
            console.print(f"[red]POST /studies failed[/red]: {post.status_code} {post.text}")
            raise typer.Exit(code=2)
        doc = post.json()
        study_id = doc["_id"]
        console.print(f"[green]submitted[/green]: {study_id}")

        final = _poll_until_terminal(
            client,
            path=f"/studies/{study_id}",
            terminal={"succeeded", "failed", "cancelled"},
            poll_seconds=poll_seconds,
        )

    _print_study_summary(final)
    if final.get("status") == "failed":
        raise typer.Exit(code=2)


def _print_study_summary(study_doc: dict[str, Any]) -> None:
    status = study_doc.get("status", "?")
    progress = study_doc.get("progress", {})
    console.print(
        f"[bold]status[/bold]: {status} "
        f"· {progress.get('completed', 0)}/{progress.get('total', 0)} completed"
        f" · {progress.get('failed', 0)} failed"
    )
    best = study_doc.get("best_trial")
    if not best:
        console.print("[yellow]no best trial[/yellow]")
        return
    table = Table(title="best trial", show_header=True)
    table.add_column("field")
    table.add_column("value")
    table.add_row("number", str(best.get("number")))
    table.add_row("value", f"{float(best.get('value', 0.0)):.4f}")
    table.add_row("run_id", str(best.get("run_id") or "—"))
    for k, v in (best.get("params") or {}).items():
        table.add_row(f"param.{k}", str(v))
    console.print(table)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
