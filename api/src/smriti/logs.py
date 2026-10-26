"""Structured logging with the current item id on every line."""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

from smriti.config import get_settings

current_item_id: ContextVar[str | None] = ContextVar("current_item_id", default=None)
current_step: ContextVar[str | None] = ContextVar("current_step", default=None)


class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.item_id = current_item_id.get()
        record.step = current_step.get()
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in ("item_id", "step"):
            if value := getattr(record, key, None):
                line[key] = value
        if extra := getattr(record, "data", None):
            line.update(extra)
        if record.exc_info:
            line["exc"] = self.formatException(record.exc_info)
        return json.dumps(line, default=str)


def setup_logging() -> None:
    settings = get_settings()
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_ContextFilter())
    handler.setFormatter(
        _JsonFormatter()
        if settings.log_json
        else logging.Formatter("%(asctime)s %(levelname)s %(name)s [%(item_id)s] %(message)s")
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(settings.log_level)
    for noisy in ("httpx", "httpcore", "botocore", "boto3", "urllib3", "trafilatura"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
