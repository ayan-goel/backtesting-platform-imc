"""/strategies router: upload, list, get, delete Python `Trader` files."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from engine.errors import StrategyLoadError
from engine.simulator.strategy_params import extract_tunable_params
from server.deps import get_app_settings, get_db
from server.services import strategy_service
from server.services.strategy_service import StrategyBusyError
from server.settings import Settings
from server.storage import registry

router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.get("")
async def list_all(db: Any = Depends(get_db)) -> list[dict[str, Any]]:
    return await strategy_service.list_strategies(db)


@router.post("", status_code=201)
async def upload(
    file: UploadFile = File(..., description="A .py file containing a Trader class"),
    db: Any = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> dict[str, Any]:
    content = await file.read()
    try:
        return await strategy_service.upload_strategy(
            filename=file.filename or "strategy.py",
            content=content,
            settings=settings,
            db=db,
        )
    except StrategyLoadError as e:
        raise HTTPException(status_code=400, detail=f"invalid strategy: {e}") from e


@router.get("/{strategy_id}")
async def get_one(strategy_id: str, db: Any = Depends(get_db)) -> dict[str, Any]:
    doc = await strategy_service.get_strategy(db, strategy_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"no strategy {strategy_id!r}")
    return doc


@router.get("/{strategy_id}/params")
async def detect_params(
    strategy_id: str,
    db: Any = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> list[dict[str, Any]]:
    """Autodetect tunable UPPER_CASE class constants in the strategy file.

    Returns an ordered list suitable for prefilling the study-creation search
    space. Never raises on extraction errors — a malformed strategy just yields
    an empty list — but 404s if the strategy itself isn't registered.
    """
    doc = await strategy_service.get_strategy(db, strategy_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"no strategy {strategy_id!r}")
    path = strategy_service.resolve_strategy_path(settings, doc)
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"strategy file missing on disk for {strategy_id!r}",
        )
    params = extract_tunable_params(path)
    return [
        {
            "name": p.name,
            "class_name": p.class_name,
            "default": p.default,
            "type": p.type,
            "suggested_low": p.suggested_low,
            "suggested_high": p.suggested_high,
        }
        for p in params
    ]


@router.get("/{strategy_id}/delete-preview")
async def delete_preview(
    strategy_id: str, db: Any = Depends(get_db)
) -> dict[str, int]:
    """Return the counts that would be deleted by a cascading strategy delete."""
    doc = await strategy_service.get_strategy(db, strategy_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"no strategy {strategy_id!r}")
    return {
        "runs": await registry.count_runs_by_strategy(db, strategy_id=strategy_id),
        "batches": await registry.count_batches_by_strategy(
            db, strategy_id=strategy_id
        ),
        "studies": await registry.count_studies_by_strategy(
            db, strategy_id=strategy_id
        ),
    }


@router.delete("/{strategy_id}", status_code=204)
async def delete_one(
    strategy_id: str,
    db: Any = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> None:
    try:
        found = await strategy_service.delete_strategy(
            strategy_id=strategy_id, settings=settings, db=db
        )
    except StrategyBusyError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    if not found:
        raise HTTPException(status_code=404, detail=f"no strategy {strategy_id!r}")
