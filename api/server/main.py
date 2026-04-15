"""FastAPI app entry point. Lifespan owns the Mongo client."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from motor.motor_asyncio import AsyncIOMotorClient

from server.auth import require_api_key
from server.deps import get_db
from server.routers import batches, datasets, mc, runs, strategies, studies
from server.services.batch_runner import (
    recover_orphaned_tasks,
    start_workers,
    stop_workers,
)
from server.services.mc_runner import (
    recover_orphaned_mc,
    start_mc_worker,
    stop_mc_worker,
)
from server.services.study_runner import StudyRunnerState
from server.services.study_runner import stop_all as stop_studies
from server.services.study_service import resume_running_studies
from server.settings import get_settings
from server.storage.registry import ensure_indexes


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    client: AsyncIOMotorClient[Any] = AsyncIOMotorClient(settings.mongo_url)
    db = client[settings.mongo_db]
    app.state.mongo_client = client
    app.state.mongo_db = db
    await ensure_indexes(db)
    await recover_orphaned_tasks(db)
    await recover_orphaned_mc(db)
    workers = await start_workers(db=db, settings=settings)
    app.state.batch_workers = workers
    study_runner_state = StudyRunnerState()
    app.state.study_runner = study_runner_state
    await resume_running_studies(
        db=db, settings=settings, runner_state=study_runner_state
    )
    mc_state = await start_mc_worker(db=db, settings=settings)
    app.state.mc_worker = mc_state
    try:
        yield
    finally:
        await stop_mc_worker(mc_state)
        await stop_studies(study_runner_state)
        await stop_workers(workers)
        client.close()


app = FastAPI(title="Prosperity Platform API", version="0.1.0", lifespan=lifespan)

app.add_middleware(GZipMiddleware, minimum_size=1024)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health(db: Any = Depends(get_db)) -> dict[str, Any]:
    """Unauthenticated health check. Pings Mongo."""
    ping = await db.command("ping")
    return {"status": "ok", "mongo": ping}


app.include_router(runs.router, dependencies=[Depends(require_api_key)])
app.include_router(datasets.router, dependencies=[Depends(require_api_key)])
app.include_router(strategies.router, dependencies=[Depends(require_api_key)])
app.include_router(batches.router, dependencies=[Depends(require_api_key)])
app.include_router(studies.router, dependencies=[Depends(require_api_key)])
app.include_router(mc.router, dependencies=[Depends(require_api_key)])
