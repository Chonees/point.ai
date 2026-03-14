"""
observability.py
Structured logging helpers for the v2 pipeline.
"""
from __future__ import annotations

import json
import logging
from typing import Any


LOGGER_NAME = "pointai"


def get_logger(name: str = LOGGER_NAME) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


def log_event(event: str, **fields: Any) -> None:
    payload = {"event": event, **_normalize_fields(fields)}
    get_logger().info(json.dumps(payload, sort_keys=True))


def _normalize_fields(fields: dict[str, Any]) -> dict[str, Any]:
    normalized = {}
    for key, value in fields.items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            normalized[key] = value
        elif isinstance(value, dict):
            normalized[key] = _normalize_fields(value)
        elif isinstance(value, (list, tuple)):
            normalized[key] = [
                item if isinstance(item, (str, int, float, bool)) or item is None else str(item)
                for item in value
            ]
        else:
            normalized[key] = str(value)
    return normalized
