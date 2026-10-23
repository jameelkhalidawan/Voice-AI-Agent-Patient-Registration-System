"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import install_exception_handlers
from app.api.middleware import RequestGuardMiddleware
from app.api.routes.patients import router as patients_router
from app.api.schemas import success
from app.config import get_settings
from app.logging_config import configure_logging
from app.telephony.webhook import router as vapi_router

settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Log application startup and shutdown."""

    logger.info("application_starting", extra={"call_id": ""})
    yield
    logger.info("application_stopping", extra={"call_id": ""})


app = FastAPI(title=settings.app_name, lifespan=lifespan)
install_exception_handlers(app)
app.add_middleware(RequestGuardMiddleware)
origins = [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]
if origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-API-Key"],
    )
app.include_router(patients_router)
app.include_router(vapi_router)


@app.get("/health", tags=["health"])
def health_check() -> dict[str, object]:
    """Return a minimal liveness response."""

    return success({"status": "ok"})
