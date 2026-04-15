.PHONY: sync test lint typecheck cli serve clean

sync:
	uv sync

test:
	uv run pytest -q

lint:
	uv run ruff check engine server cli tests

typecheck:
	uv run mypy engine server cli

cli:
	uv run prosperity --help

serve:
	uv run uvicorn server.main:app --reload --port 8000

clean:
	rm -rf .venv .pytest_cache .ruff_cache .mypy_cache dist *.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
