import logging

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class AppException(Exception):
    """Base application exception."""

    def __init__(
        self,
        status_code: int = 500,
        error_code: str = "INTERNAL_ERROR",
        detail: str = "An unexpected error occurred",
    ) -> None:
        self.status_code = status_code
        self.error_code = error_code
        self.detail = detail
        super().__init__(detail)


class NotFoundException(AppException):
    """Resource not found."""

    def __init__(self, detail: str = "Resource not found") -> None:
        super().__init__(status_code=404, error_code="NOT_FOUND", detail=detail)


class ValidationException(AppException):
    """Validation error."""

    def __init__(self, detail: str = "Validation error") -> None:
        super().__init__(status_code=422, error_code="VALIDATION_ERROR", detail=detail)


class ForbiddenException(AppException):
    """Action not allowed."""

    def __init__(
        self,
        detail: str = "Action not allowed",
        error_code: str = "FORBIDDEN",
    ) -> None:
        super().__init__(status_code=403, error_code=error_code, detail=detail)


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handle custom application exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "error_code": exc.error_code},
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions with logging."""
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error_code": "INTERNAL_ERROR"},
    )
