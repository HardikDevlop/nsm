"""Read-only Windows System event collection over the verified WinRM adapter."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import re
from typing import Any, Protocol

from .winrm import WinRMHTTPSAdapter


logger = logging.getLogger(__name__)
_DOTNET_DATE = re.compile(r"^/Date\((-?\d+)([+-]\d{4})?\)/$")
_ISO_LIKE = re.compile(r"^\d{4}-\d{2}-\d{2}T")
_ISO_FRACTION = re.compile(r"\.(\d{7,})(?=(?:Z|[+-]\d{2}:\d{2})$)")
_POWERSHELL_DATETIME_LIKE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
_LOCALE_DATETIME_LIKE = re.compile(r"^(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|[A-Za-z]{3,9}[ ,]+\d{1,2}[ ,]+\d{2,4})")


def _timestamp_representation(value: Any) -> tuple[str, str]:
    if value is None:
        return "null", "none"
    if isinstance(value, bool):
        return "numeric", "boolean"
    if isinstance(value, (int, float)):
        return "numeric", "number"
    if isinstance(value, str):
        text = value.strip().replace("Z", "+00:00")
        if _DOTNET_DATE.fullmatch(text):
            return "string", "dotnet_date"
        if _ISO_LIKE.match(text):
            return "string", "iso_like"
        if _POWERSHELL_DATETIME_LIKE.match(text):
            return "string", "powershell_datetime_like"
        if _LOCALE_DATETIME_LIKE.match(text):
            return "string", "locale_datetime_like"
        try:
            datetime.fromisoformat(text)
        except ValueError:
            return "string", "unknown"
        return "string", "iso_like"
    if isinstance(value, dict):
        return "object", "mapping"
    if isinstance(value, (list, tuple)):
        return "array", "sequence"
    return "object", "unsupported"


def _log_timestamp_rejection(value: Any, reason: str) -> None:
    representation, format_category = _timestamp_representation(value)
    logger.warning(
        "windows_system_event_timestamp_rejected field=time_created representation=%s format=%s reason=%s",
        representation,
        format_category,
        reason,
    )


class SystemEventTransport(Protocol):
    def query_system_events(self, *, start_time: str, end_time: str, event_ids: tuple[int, ...], max_records: int) -> tuple[bytes, bytes, int]: ...


class SystemEventError(Exception):
    def __init__(self, category: str, message: str, *, field: str | None = None, reason: str | None = None):
        super().__init__(message)
        self.category = category
        self.message = message
        self.field = field
        self.reason = reason


@dataclass(frozen=True)
class SystemEvent:
    record_id: int
    time_created: str
    event_id: int
    provider: str | None
    level: str | None
    machine_name: str | None
    message: str | None
    user_id: str | None


@dataclass(frozen=True)
class SystemEventCollection:
    events: tuple[SystemEvent, ...]
    event_count: int
    truncated: bool
    collected_at: str


def _iso_with_timezone(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        reason = "missing" if value is None or (isinstance(value, str) and not value.strip()) else "invalid_format"
        _log_timestamp_rejection(value, reason)
        raise SystemEventError("malformed", "System event time_created is missing", field="time_created", reason=reason)
    text = value.strip().replace("Z", "+00:00")
    dotnet_date = _DOTNET_DATE.fullmatch(text)
    if dotnet_date:
        try:
            milliseconds = int(dotnet_date.group(1))
            parsed = datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            _log_timestamp_rejection(value, "invalid_format")
            raise SystemEventError("malformed", "System event time_created is invalid", field="time_created", reason="invalid_format") from None
        return parsed.isoformat()
    # Python 3.10 accepts at most six fractional-second digits. Windows/.NET
    # can emit seven; retain microsecond precision and preserve the offset.
    text = _ISO_FRACTION.sub(lambda match: "." + match.group(1)[:6], text)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        _log_timestamp_rejection(value, "invalid_format")
        raise SystemEventError("malformed", "System event time_created is invalid", field="time_created", reason="invalid_format") from None
    if parsed.tzinfo is None:
        _log_timestamp_rejection(value, "missing_timezone")
        raise SystemEventError("malformed", "System event time_created has no timezone", field="time_created", reason="missing_timezone")
    return parsed.isoformat()


def _optional_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _normalize(raw: Any) -> SystemEvent:
    if not isinstance(raw, dict):
        raise SystemEventError("malformed", "System event record is not an object", field="event", reason="not_object")
    try:
        record_id = int(raw["record_id"])
    except (KeyError, TypeError, ValueError):
        raise SystemEventError("malformed", "System event identifiers are invalid", field="record_id", reason="missing_or_invalid") from None
    try:
        event_id = int(raw["event_id"])
    except (KeyError, TypeError, ValueError):
        raise SystemEventError("malformed", "System event identifiers are invalid", field="event_id", reason="missing_or_invalid") from None
    if record_id < 0 or event_id < 0:
        field = "record_id" if record_id < 0 else "event_id"
        raise SystemEventError("malformed", "System event identifiers are invalid", field=field, reason="negative")
    return SystemEvent(
        record_id=record_id,
        time_created=_iso_with_timezone(raw.get("time_created")),
        event_id=event_id,
        provider=_optional_text(raw.get("provider")),
        level=_optional_text(raw.get("level")),
        machine_name=_optional_text(raw.get("machine_name")),
        message=_optional_text(raw.get("message")),
        user_id=_optional_text(raw.get("user_id")),
    )


def collect_system_events(
    transport: SystemEventTransport,
    *,
    start_time: datetime,
    end_time: datetime,
    event_ids: tuple[int, ...] = (),
    max_records: int = 100,
) -> SystemEventCollection:
    """Collect bounded System events; zero results are a successful collection."""
    if start_time.tzinfo is None or end_time.tzinfo is None or start_time > end_time:
        raise SystemEventError("invalid_range", "System event time range is invalid")
    if not 1 <= max_records <= 500:
        raise SystemEventError("invalid_limit", "System event record limit is invalid")
    if len(set(event_ids)) != len(event_ids) or any(not isinstance(item, int) or isinstance(item, bool) or item < 0 for item in event_ids):
        raise SystemEventError("invalid_filter", "System event IDs are invalid")
    try:
        stdout, stderr, status = transport.query_system_events(
            start_time=start_time.isoformat(),
            end_time=end_time.isoformat(),
            event_ids=event_ids,
            max_records=max_records,
        )
    except Exception as exc:
        category = WinRMHTTPSAdapter._classify(exc).category
        logger.warning(
            "windows_system_event_collection_failure stage=transport exception_type=%s category=%s",
            type(exc).__name__, category,
        )
        raise SystemEventError(category, "Windows System event collection failed") from None
    if status != 0:
        error_text = stderr.decode("utf-8", errors="replace").lower()
        category = "permission" if "access" in error_text or "denied" in error_text else "unavailable"
        logger.warning(
            "windows_system_event_command_failed stage=command_output status=%s category=%s",
            status, category,
        )
        raise SystemEventError(category, "Windows System event collection failed")
    try:
        payload = json.loads(stdout.decode("utf-8"))
        raw_events = payload.get("events") if isinstance(payload, dict) else None
        if isinstance(raw_events, dict):
            raw_events = [raw_events]
        if not isinstance(raw_events, list):
            raise SystemEventError("malformed", "Windows System event output was malformed", field="events", reason="not_array")
        if not isinstance(payload.get("truncated"), bool):
            raise SystemEventError("malformed", "Windows System event output was malformed", field="truncated", reason="not_boolean")
        events = tuple(_normalize(item) for item in raw_events)
    except SystemEventError as exc:
        logger.warning(
            "windows_system_event_parse_failure stage=event_validation exception_type=%s category=%s field=%s reason=%s",
            type(exc).__name__,
            exc.category,
            exc.field or "unknown",
            exc.reason or "unknown",
        )
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError, AttributeError) as exc:
        logger.warning(
            "windows_system_event_parse_failure stage=json_decode exception_type=%s category=malformed",
            type(exc).__name__,
        )
        raise SystemEventError("malformed", "Windows System event output was malformed") from None
    return SystemEventCollection(
        events=events,
        event_count=len(events),
        truncated=payload["truncated"],
        collected_at=datetime.now(timezone.utc).isoformat(),
    )
