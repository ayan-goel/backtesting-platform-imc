"""FastAPI dependencies: Mongo client, database, settings."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from server.settings import Settings, get_settings


def get_app_settings() -> Settings:
    return get_settings()


def get_mongo_client(request: Request) -> Any:
    """Return the motor client attached to the app lifespan."""
    client: AsyncIOMotorClient[Any] = request.app.state.mongo_client
    return client


def get_db(request: Request) -> Any:
    """Return the motor database attached to the app lifespan."""
    db: AsyncIOMotorDatabase[Any] = request.app.state.mongo_db
    return db


def get_batch_workers(request: Request) -> Any:
    """Return the batch workers state (with wakeup event). None when workers
    aren't running (e.g. tests that don't start the executor)."""
    return getattr(request.app.state, "batch_workers", None)


def get_study_runner(request: Request) -> Any:
    """Return the study runner state. None when not bootstrapped
    (e.g. tests that don't start studies)."""
    return getattr(request.app.state, "study_runner", None)
