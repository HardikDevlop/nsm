"""Canonical time helpers for the monitoring foundation.

New application timestamps are aware UTC values. Legacy naive values are not
silently guessed; callers must provide their known semantic when normalizing.
"""
from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None, *, legacy: str | None = None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        if legacy == "UTC_NAIVE":
            return value.replace(tzinfo=timezone.utc)
        raise ValueError("naive timestamp requires an explicit legacy semantic")
    return value.astimezone(timezone.utc)


def iso_utc(value: datetime | None, *, legacy: str | None = None) -> str | None:
    normalized = as_utc(value, legacy=legacy)
    return normalized.isoformat().replace("+00:00", "Z") if normalized else None
