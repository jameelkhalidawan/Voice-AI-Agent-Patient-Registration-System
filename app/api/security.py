"""Write-endpoint API-key authentication."""

import hmac

from fastapi import Header, HTTPException

from app.config import get_settings


def require_write_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    """Require a configured API key and compare it without timing leaks."""

    expected = get_settings().api_key
    if not expected:
        raise HTTPException(status_code=503, detail="Write API key is not configured.")
    if x_api_key is None or not hmac.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")
