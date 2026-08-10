"""File logging for module diagnostics and realtime monitoring."""

from __future__ import annotations

import logging
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler


def configure_logging() -> None:
    log_dir = Path(__file__).resolve().parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if any(isinstance(handler, logging.FileHandler) and str(log_dir) in handler.baseFilename for handler in root.handlers):
        return
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    root_file = TimedRotatingFileHandler(
        log_dir / "events.log", when="midnight", interval=1,
        backupCount=31, encoding="utf-8", delay=True,
    )
    root_file.suffix = "%Y-%m-%d"
    root_file.setFormatter(formatter)
    root.addHandler(root_file)
    for module, filename in {
        "backend.api": "api.log",
        "discovery_modules.icmp_discovery": "icmp.log",
        "backend.snmp": "snmp.log",
        "discovery_modules.device_profiler": "device_profiler.log",
        "backend.services.realtime_monitor": "realtime_monitor.log",
        "monitoring_modules.trap_receiver": "traps.log",
    }.items():
        logger = logging.getLogger(module)
        logger.setLevel(logging.INFO)
        handler = TimedRotatingFileHandler(
            log_dir / filename, when="midnight", interval=1,
            backupCount=31, encoding="utf-8", delay=True,
        )
        handler.suffix = "%Y-%m-%d"
        handler.setFormatter(formatter)
        logger.addHandler(handler)
