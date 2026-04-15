"""/batches router: create, list, fetch."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from server.deps import get_app_settings, get_batch_workers, get_db
from server.schemas.batches import BatchCreateRequest
from server.services import batch_runner, batch_service
from server.services.batch_service import BatchBusyError
from server.services.run_service import DatasetNotFoundError, StrategyNotFoundError
from server.settings import Settings

router = APIRouter(prefix="/batches", tags=["batches"])


@router.get("")
async def list_all(
    skip: int = 0, limit: int = 50, db: Any = Depends(get_db)
) -> list[dict[str, Any]]:
    return await batch_service.list_batches(db, skip=skip, limit=limit)


@router.post("", status_code=201)
async def create(
    req: BatchCreateRequest,
    db: Any = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
    workers: Any = Depends(get_batch_workers),
) -> dict[str, Any]:
    try:
        doc = await batch_service.create_batch(req=req, settings=settings, db=db)
    except (StrategyNotFoundError, DatasetNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    if workers is not None:
        batch_runner.signal_new_work(workers)
    return doc


@router.get("/{batch_id}")
async def get_one(batch_id: str, db: Any = Depends(get_db)) -> dict[str, Any]:
    doc = await batch_service.get_batch(db, batch_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"batch not found: {batch_id}")
    return doc


@router.delete("/{batch_id}", status_code=204)
async def delete_one(
    batch_id: str,
    db: Any = Depends(get_db),
) -> None:
    try:
        found = await batch_service.delete_batch(db=db, batch_id=batch_id)
    except BatchBusyError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    if not found:
        raise HTTPException(status_code=404, detail=f"batch not found: {batch_id}")
