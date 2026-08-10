"""Structured SNMP operation logging helpers."""

import logging
import time
from contextlib import contextmanager
from typing import Iterator

logger = logging.getLogger("nms.snmp")


@contextmanager
def operation(name: str, **fields: object) -> Iterator[None]:
    """Log operation start, duration, and failure without logging secrets."""
    started = time.perf_counter()
    logger.info("snmp_operation_start name=%s fields=%s", name, fields)
    try:
        yield
    except Exception:
        logger.exception("snmp_operation_failed name=%s duration_ms=%.2f", name, (time.perf_counter() - started) * 1000)
        raise
    else:
        logger.info("snmp_operation_complete name=%s duration_ms=%.2f", name, (time.perf_counter() - started) * 1000)
