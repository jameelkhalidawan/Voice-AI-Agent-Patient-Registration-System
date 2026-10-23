"""Small in-process request-size and fixed-window rate limiting middleware."""

from collections import defaultdict
from time import monotonic

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import get_settings


class RequestGuardMiddleware(BaseHTTPMiddleware):
    """Limit oversized bodies and basic per-client request bursts."""

    def __init__(self, app):
        """Initialize the per-process rate-limit counters."""

        super().__init__(app)
        self.windows: dict[str, tuple[int, int]] = defaultdict(lambda: (0, 0))

    async def dispatch(self, request: Request, call_next):
        """Enforce configured request size and per-minute request limit."""

        settings = get_settings()
        length = request.headers.get("content-length")
        max_bytes = (
            settings.max_webhook_request_bytes
            if request.url.path == "/webhook/vapi"
            else settings.max_request_bytes
        )
        if length and length.isdigit() and int(length) > max_bytes:
            return JSONResponse(
                status_code=413,
                content={"data": None, "error": {"code": "REQUEST_TOO_LARGE", "message": "The request is too large.", "fields": {}}},
            )
        now = int(monotonic() // 60)
        client = request.client.host if request.client else "unknown"
        count, window = self.windows[client]
        if window != now:
            count, window = 0, now
        if count >= settings.rate_limit_per_minute:
            return JSONResponse(
                status_code=429,
                content={"data": None, "error": {"code": "RATE_LIMITED", "message": "Too many requests. Please try again shortly.", "fields": {}}},
            )
        self.windows[client] = (count + 1, window)
        return await call_next(request)
