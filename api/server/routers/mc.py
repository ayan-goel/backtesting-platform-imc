"""/mc router: create, list, fetch, cancel, delete MC simulations."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from server.deps import get_app_settings, get_db, get_mc_worker
from server.schemas.mc import McCreateRequest
from server.services import mc_runner, mc_service
from server.services.mc_service import McBusyError
from server.services.run_service import DatasetNotFoundError, StrategyNotFoundError
from server.settings import Settings
from server.storage import mc_artifacts

router = APIRouter(prefix="/mc", tags=["mc"])


@router.get("")
async def list_all(
    skip: int = 0, limit: int = 50, db: Any = Depends(get_db)
) -> list[dict[str, Any]]:
    return await mc_service.list_mc_simulations(db, skip=skip, limit=limit)


@router.post("", status_code=201)
async def create(
    req: McCreateRequest,
    db: Any = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
    worker: Any = Depends(get_mc_worker),
) -> dict[str, Any]:
    try:
        doc = await mc_service.create_mc_simulation(req=req, settings=settings, db=db)
    except (StrategyNotFoundError, DatasetNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    if worker is not None:
        mc_runner.signal_new_mc_work(worker)
    return doc


@router.get("/{mc_id}")
async def get_one(mc_id: str, db: Any = Depends(get_db)) -> dict[str, Any]:
    doc = await mc_service.get_mc_simulation(db, mc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"mc simulation not found: {mc_id}")
    return doc


@router.post("/{mc_id}/cancel")
async def cancel(mc_id: str, db: Any = Depends(get_db)) -> dict[str, Any]:
    doc = await mc_service.cancel_mc_simulation(db, mc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"mc simulation not found: {mc_id}")
    return doc


@router.delete("/{mc_id}", status_code=204)
async def delete_one(
    mc_id: str,
    db: Any = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> None:
    try:
        found = await mc_service.delete_mc_simulation(
            db=db, settings=settings, mc_id=mc_id
        )
    except McBusyError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    if not found:
        raise HTTPException(status_code=404, detail=f"mc simulation not found: {mc_id}")


@router.get("/{mc_id}/config")
async def get_config(
    mc_id: str,
    settings: Settings = Depends(get_app_settings),
) -> dict[str, Any]:
    cfg = mc_artifacts.read_config(settings.storage_root, mc_id)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"config not found for mc: {mc_id}")
    return cfg


@router.get("/{mc_id}/paths/{index}/curve")
async def get_path_curve(
    mc_id: str,
    index: int,
    settings: Settings = Depends(get_app_settings),
) -> dict[str, Any]:
    curve = mc_artifacts.read_path_curve(settings.storage_root, mc_id, index)
    if curve is None:
        raise HTTPException(
            status_code=404,
            detail=f"curve not found for mc={mc_id!r} index={index}",
        )
    return {"index": index, "curve": curve.tolist()}
