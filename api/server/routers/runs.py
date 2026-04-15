"""/runs router: list, create, summary, and event streaming."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from server.deps import get_app_settings, get_db
from server.schemas.runs import RunCreateRequest
from server.services import run_service
from server.services.run_service import (
    DatasetNotFoundError,
    RunBusyError,
    StrategyNotFoundError,
    execute_run,
)
from server.settings import Settings
from server.storage import artifacts, registry

router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("")
async def list_runs(
    skip: int = 0,
    limit: int = 50,
    db: Any = Depends(get_db),
) -> list[dict[str, Any]]:
    return await registry.list_runs(db, skip=skip, limit=limit)


@router.post("", status_code=201)
async def create_run(
    req: RunCreateRequest,
    db: Any = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> dict[str, Any]:
    try:
        return await execute_run(req=req, settings=settings, db=db)
    except (DatasetNotFoundError, StrategyNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.delete("/{run_id}", status_code=204)
async def delete_run_route(
    run_id: str,
    db: Any = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> None:
    try:
        found = await run_service.delete_run(db=db, settings=settings, run_id=run_id)
    except RunBusyError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    if not found:
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")


@router.get("/{run_id}/summary")
async def get_summary(run_id: str, db: Any = Depends(get_db)) -> dict[str, Any]:
    doc = await registry.get_run(db, run_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}")
    return doc


@router.get("/{run_id}/config")
async def get_config(
    run_id: str,
    settings: Settings = Depends(get_app_settings),
) -> dict[str, Any]:
    cfg = artifacts.read_config(settings.storage_root, run_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"config not found for run: {run_id}")
    return cfg


@router.get("/{run_id}/events")
async def get_events(
    run_id: str,
    product: str | None = Query(default=None),
    ts_from: int | None = Query(default=None),
    ts_to: int | None = Query(default=None),
    limit: int | None = Query(default=None),
    offset: int = Query(default=0),
    stride: int = Query(default=1, ge=1),
    settings: Settings = Depends(get_app_settings),
) -> StreamingResponse:
    """Stream matching event records as JSONL."""
    has_filters = (
        product is not None
        or ts_from is not None
        or ts_to is not None
        or limit is not None
        or offset != 0
        or stride != 1
    )

    if not has_filters:
        # Fast path: no filtering, so avoid parsing + re-serializing every line.
        # Stream the raw file straight to the client.
        path = artifacts.run_dir(settings.storage_root, run_id) / "events.jsonl"
        if not path.is_file():
            return StreamingResponse(iter(()), media_type="application/x-ndjson")

        def _raw() -> Iterator[bytes]:
            with path.open("rb") as fh:
                while chunk := fh.read(65536):
                    yield chunk

        return StreamingResponse(_raw(), media_type="application/x-ndjson")

    def _gen() -> Iterator[str]:
        for record in artifacts.iter_events(
            settings.storage_root,
            run_id,
            product=product,
            ts_from=ts_from,
            ts_to=ts_to,
            limit=limit,
            offset=offset,
            stride=stride,
        ):
            yield json.dumps(record, separators=(",", ":")) + "\n"

    return StreamingResponse(_gen(), media_type="application/x-ndjson")


@router.get("/{run_id}/events/count")
async def events_count(
    run_id: str,
    settings: Settings = Depends(get_app_settings),
) -> dict[str, int]:
    return {"count": artifacts.count_events(settings.storage_root, run_id)}
