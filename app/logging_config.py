"""Small JSON-ish stdout logging setup with optional call context."""

import json
import logging
from datetime import datetime, timezone
from typing import Any


class JsonLineFormatter(logging.Formatter):
    """Format each log record as one JSON object, including call_id if present."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialize a log record without adding application payloads."""

        entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        call_id = getattr(record, "call_id", None)
        if call_id:
            entry["call_id"] = call_id
        # The final confirmed registration payload is intentionally logged for
        # the assessment requirement; other arbitrary record extras stay hidden.
        final_payload = getattr(record, "final_payload", None)
        if final_payload is not None:
            entry["final_payload"] = final_payload
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    """Configure root logging to emit JSON-ish lines to stdout."""

    handler = logging.StreamHandler()
    handler.setFormatter(JsonLineFormatter())
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level.upper())
