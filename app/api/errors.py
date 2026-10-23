"""Consistent API exception handlers and error envelope helpers."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.schemas import success
from app.services.patients import DuplicatePhoneError, PatientNotFoundError
from app.services.validation import FieldValidationError

logger = logging.getLogger(__name__)


def error_response(
    status_code: int,
    code: str,
    message: str,
    fields: dict[str, str] | None = None,
) -> JSONResponse:
    """Build the standard error envelope."""

    return JSONResponse(
        status_code=status_code,
        content={"data": None, "error": {"code": code, "message": message, "fields": fields or {}}},
    )


def install_exception_handlers(app: FastAPI) -> None:
    """Install application-wide handlers so errors never leak raw traces."""

    @app.exception_handler(FieldValidationError)
    async def field_validation_handler(_: Request, exc: FieldValidationError) -> JSONResponse:
        return error_response(422, "VALIDATION_ERROR", "Please correct the highlighted fields.", {exc.field: exc.message})

    @app.exception_handler(DuplicatePhoneError)
    async def duplicate_handler(_: Request, exc: DuplicatePhoneError) -> JSONResponse:
        return error_response(409, "DUPLICATE_PHONE", str(exc), {"phone_number": str(exc)})

    @app.exception_handler(PatientNotFoundError)
    async def not_found_handler(_: Request, exc: PatientNotFoundError) -> JSONResponse:
        return error_response(404, "NOT_FOUND", str(exc))

    @app.exception_handler(RequestValidationError)
    async def request_validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Invalid JSON shape, path/query coercion, and missing bodies are malformed requests.
        fields: dict[str, str] = {}
        for item in exc.errors():
            loc = item.get("loc", ())
            key = str(loc[-1]) if loc else "request"
            fields[key] = "The request value is missing or has an invalid format."
        return error_response(400, "MALFORMED_REQUEST", "The request could not be parsed.", fields)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        mapping = {
            401: ("UNAUTHORIZED", "A valid API key is required."),
            403: ("FORBIDDEN", "This request is not allowed."),
            404: ("NOT_FOUND", "The requested resource was not found."),
            413: ("REQUEST_TOO_LARGE", "The request is too large."),
            429: ("RATE_LIMITED", "Too many requests. Please try again shortly."),
            503: ("CONFIGURATION_ERROR", "The service is not configured for this operation."),
        }
        code, message = mapping.get(exc.status_code, ("HTTP_ERROR", "The request could not be completed."))
        return error_response(exc.status_code, code, message)

    @app.exception_handler(Exception)
    async def unexpected_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_api_error", extra={"call_id": ""})
        return error_response(500, "INTERNAL_ERROR", "An unexpected server error occurred.")
