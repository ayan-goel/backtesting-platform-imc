# Backtesting Platform — IMC Prosperity 4

A backtesting engine, FastAPI service, and web dashboard for developing and evaluating
trading strategies for the [IMC Prosperity 4](https://prosperity.imc.com/) competition.

- **Engine** — replays historical order books against your strategy, tracks PnL and
  inventory, and enforces position limits.
- **API + CLI** — run single backtests, sweep parameters with Optuna-backed grid search,
  and persist results to MongoDB.
- **Dashboard** — inspect a run's trades, PnL curves, and order-book snapshots in the
  browser.

## Repo layout

```
api/         Python package — engine, FastAPI server, Typer CLI
dashboard/   Next.js 15 + React 19 + Tailwind frontend
```

Each subproject has its own `claude.md` with stack-specific conventions.

## Getting started

### Prerequisites

- Python **3.11+** and [`uv`](https://docs.astral.sh/uv/)
- Node **20+** and [`pnpm`](https://pnpm.io/)
- MongoDB (local or remote) — see [api/.env.example](api/.env.example)

### api

```bash
cd api
cp .env.example .env        # fill in MongoDB + any secrets
make sync                   # install deps into .venv
make serve                  # FastAPI on http://localhost:8000
make cli                    # show the `prosperity` CLI
```

Other targets: `make test`, `make lint`, `make typecheck`.

### dashboard

```bash
cd dashboard
cp .env.local.example .env.local   # point at the API
pnpm install
pnpm dev                           # http://localhost:3000
```

Other scripts: `pnpm build`, `pnpm test`, `pnpm lint`, `pnpm typecheck`.

## Running a backtest

With the API running:

```bash
cd api
uv run prosperity --help
```

The CLI wraps the same endpoints the dashboard uses, so runs triggered either way land
in the same MongoDB collection and show up in the UI.
