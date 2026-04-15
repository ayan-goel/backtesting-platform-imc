"""Structured event logging. T6 ships JSONL writer + submission-safe no-op logger."""

from engine.logging.event_log import EventLogger, EventRecord, NoOpLogger

__all__ = ["EventLogger", "EventRecord", "NoOpLogger"]
