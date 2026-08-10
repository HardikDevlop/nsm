---
kind: logging_system
name: Centralized Python Logging with File and Console Sinks
category: logging_system
scope:
    - '**'
source_files:
    - icmp_discovery/logger.py
    - icmp_discovery/config.py
    - icmp_discovery/main.py
    - icmp_discovery/discovery_manager.py
    - icmp_discovery/tests/test_logger.py
---

The repository implements a centralized logging system for the ICMP Discovery Service (the Python backend component) using Python's built-in `logging` module, wrapped in a thin utility layer that provides both file and console output.

**System and framework**
- Uses Python standard library `logging` — no third-party logging framework is imported.
- A single logger instance named `icmp_discovery` is created in `icmp_discovery/logger.py`, configured at import time with DEBUG level and handlers attached only once (`if not _LOGGER.handlers`).
- Two sinks are registered: a `FileHandler` writing to a date-stamped file under `data/logs/icmp_YYYYMMDD.log` and a `StreamHandler` writing to stdout. Both use the same formatter.
- The formatter produces a pipe-delimited line with fields: `asctime | threadName | module | funcName | levelname | message`.

**Architecture and initialization**
- `logger.py` is imported by entry points and orchestrators (e.g., `main.py`, `discovery_manager.py`) which call convenience functions `info()`, `success()`, `warning()`, `error()`, `debug()`, `critical()` rather than calling `logging.getLogger(...)` directly.
- `_write()` wraps each log call in a `threading.Lock` to ensure thread-safe writes across concurrent discovery workers.
- Log directory `LOG_FOLDER` is read from `config.LOG_FOLDER` (`"data/logs/"`) and created on import if it does not exist.
- The `header()` and `sub_header()` helpers print banner-style text via plain `print()` for CLI-style output; these are not part of the structured log stream.

**Conventions observed**
- All discovery modules log through the shared `logger` module functions (`from logger import info, success, ...`) rather than creating their own loggers.
- Log messages are plain strings; there is no structured JSON payload or custom record attributes beyond what the default formatter emits.
- The `success()` function maps to the standard `INFO` level (not a distinct severity), so success and info entries are indistinguishable at the sink level.
- The Flask API (`app.py`) and FastAPI backend (`backend/main.py`) do not configure any logging; they rely on Uvicorn/Flask defaults and do not integrate the centralized logger.

**Constraints enforced by code**
- Only one set of handlers is attached per process because of the `if not _LOGGER.handlers` guard.
- `propagate = False` prevents duplicate emission to root logger handlers.
- File output is always appended (default `FileHandler` mode) and uses UTF-8 encoding.
- Thread safety is guaranteed via the module-level `_lock` around every write.

**Test coverage**
- `tests/test_logger.py` exercises all public logger functions and asserts their output appears on stdout via `capsys`.