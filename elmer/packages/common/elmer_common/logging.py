"""Structured logging configuration for Elmer services."""

import logging
import sys
from typing import Any


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
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
