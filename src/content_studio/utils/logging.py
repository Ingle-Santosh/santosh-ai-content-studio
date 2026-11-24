import json
import logging
from datetime import UTC, datetime
from typing import Any


class StructuredJSONFormatter(logging.Formatter):
    """Emits single-line JSON log records for structured observability."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("request_id", "method", "path", "status_code", "duration_ms", "project_id"):
            val = getattr(record, key, None)
            if val is not None:
                payload[key] = val
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_structured_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root.setLevel(numeric_level)

    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(StructuredJSONFormatter())
        root.addHandler(handler)
    else:
        for handler in root.handlers:
            handler.setFormatter(StructuredJSONFormatter())
