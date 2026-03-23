from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Unified API response envelope."""

    data: T | None = None
    message: str | None = None
    success: bool = True
