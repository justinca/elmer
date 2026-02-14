"""Structured logging configuration for Elmer services."""

import logging
import sys
from datetime import datetime
from typing import Any

from .timezone import LOCAL_TZ


class _LocalTimezoneFormatter(logging.Formatter):
    """Formatter that emits timestamps in the project-local timezone."""

    converter = None  # unused — we override formatTime

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:  # noqa: N802
        dt = datetime.fromtimestamp(record.created, tz=LOCAL_TZ)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.strftime("%Y-%m-%d %H:%M:%S")


def setup_logger(
    name: str,
    level: int = logging.INFO,
) -> logging.Logger:
    """Create a structured logger for an Elmer service.

    Args:
        name: Logger name (typically the service name).
        level: Logging level.

    Returns:
        A configured logger instance.
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        formatter = _LocalTimezoneFormatter(
            fmt="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S %Z",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
