"""/studies router: create, list, fetch, cancel."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from server.deps import get_app_settings, get_db, get_study_runner
from server.schemas.studies import StudyCreateRequest
from server.services import study_service
from server.services.run_service import DatasetNotFoundError, StrategyNotFoundError
from server.services.study_service import StudyBusyError
from server.services.study_space import SpaceValidationError
from server.settings import Settings

router = APIRouter(prefix="/studies", tags=["studies"])


@router.get("")
async def list_all(
    skip: int = 0, limit: int = 50, db: Any = Depends(get_db)
) -> list[dict[str, Any]]:
    return await study_service.list_studies(db, skip=skip, limit=limit)


@router.post("", status_code=201)
async def create(
    req: StudyCreateRequest,
    db: Any = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
    runner_state: Any = Depends(get_study_runner),
) -> dict[str, Any]:
    try:
        doc = await study_service.create_study(
            req=req, settings=settings, db=db, runner_state=runner_state
        )
    except (StrategyNotFoundError, DatasetNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except SpaceValidationError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return doc


@router.get("/{study_id}")
async def get_one(study_id: str, db: Any = Depends(get_db)) -> dict[str, Any]:
    doc = await study_service.get_study(db, study_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"study not found: {study_id}")
    return doc


@router.get("/{study_id}/trials")
async def list_trials_route(
    study_id: str, db: Any = Depends(get_db)
) -> list[dict[str, Any]]:
    study = await study_service.get_study(db, study_id)
    if study is None:
        raise HTTPException(status_code=404, detail=f"study not found: {study_id}")
    return await study_service.list_trials(db, study_id)


@router.post("/{study_id}/cancel")
async def cancel(study_id: str, db: Any = Depends(get_db)) -> dict[str, Any]:
    doc = await study_service.cancel_study(db, study_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"study not found: {study_id}")
    return doc


@router.delete("/{study_id}", status_code=204)
async def delete_one(
    study_id: str,
    db: Any = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> None:
    try:
        found = await study_service.delete_study(
            db=db, settings=settings, study_id=study_id
        )
    except StudyBusyError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    if not found:
        raise HTTPException(status_code=404, detail=f"study not found: {study_id}")
