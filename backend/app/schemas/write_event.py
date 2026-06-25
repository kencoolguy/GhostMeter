"""Pydantic schemas for the write-events API."""

from datetime import datetime

from pydantic import BaseModel


class WriteEventResponse(BaseModel):
    """A single recorded client write attempt."""

    timestamp: datetime
    operation: str
    address: int
    values: list[str]
    register_name: str | None = None


class WriteEventsAckResponse(BaseModel):
    """Result of acknowledging (resetting) a device's unread writes."""

    unread: int
