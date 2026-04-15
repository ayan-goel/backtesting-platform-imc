"""/datasets router: upload, list, inspect, delete (round, day) datasets."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from server.deps import get_app_settings, get_db
from server.services import dataset_service
from server.services.dataset_service import DatasetBusyError
from server.settings import Settings
from server.storage import registry

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.get("")
async def list_all(db: Any = Depends(get_db)) -> list[dict[str, Any]]:
    return await dataset_service.list_datasets(db)


@router.post("", status_code=201)
async def upload(
    files: list[UploadFile] = File(
        ..., description="Any mix of prices_round_N_day_M.csv / trades_round_N_day_M.csv"
    ),
    db: Any = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> dict[str, Any]:
    payload: list[tuple[str, bytes]] = []
    for f in files:
        content = await f.read()
        payload.append((f.filename or "", content))

    result = await dataset_service.upload_datasets(
        files=payload, settings=settings, db=db
    )
    if not result["uploaded"]:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "no datasets uploaded",
                "skipped": result["skipped"],
            },
        )
    return result


@router.get("/{round_num}/{day}")
async def get_one(
    round_num: int,
    day: int,
    db: Any = Depends(get_db),
) -> dict[str, Any]:
    doc = await dataset_service.get_dataset(db, round_num=round_num, day=day)
    if doc is None:
        raise HTTPException(
            status_code=404, detail=f"no dataset for round={round_num} day={day}"
        )
    return doc


@router.get("/{round_num}/{day}/delete-preview")
async def delete_preview(
    round_num: int,
    day: int,
    db: Any = Depends(get_db),
) -> dict[str, int]:
    """Return the counts that would be deleted by a cascading dataset delete."""
    doc = await dataset_service.get_dataset(db, round_num=round_num, day=day)
    if doc is None:
        raise HTTPException(
            status_code=404, detail=f"no dataset for round={round_num} day={day}"
        )
    return {
        "runs": await registry.count_runs_by_dataset(db, round_num=round_num, day=day),
        "batches": await registry.count_batches_by_dataset(
            db, round_num=round_num, day=day
        ),
        "studies": await registry.count_studies_by_dataset(
            db, round_num=round_num, day=day
        ),
    }


@router.delete("/{round_num}/{day}", status_code=204)
async def delete_one(
    round_num: int,
    day: int,
    db: Any = Depends(get_db),
    settings: Settings = Depends(get_app_settings),
) -> None:
    try:
        found = await dataset_service.delete_dataset(
            round_num=round_num, day=day, settings=settings, db=db
        )
    except DatasetBusyError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    if not found:
        raise HTTPException(
            status_code=404, detail=f"no dataset for round={round_num} day={day}"
        )
