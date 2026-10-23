from datetime import datetime, timezone
import json
import logging
from types import SimpleNamespace

import pytest

from backend.windows_monitoring.events import SystemEventError, collect_system_events
from backend.windows_monitoring.winrm import WinRMHTTPSAdapter


class FakeTransport:
    def __init__(self, payload, stderr=b"", status=0):
        self.payload = payload
        self.stderr = stderr
        self.status = status
        self.calls = []

    def query_system_events(self, **kwargs):
        self.calls.append(kwargs)
        return json.dumps(self.payload).encode(), self.stderr, self.status


def event(record_id=42):
    return {
        "record_id": record_id,
        "time_created": "2026-10-17T12:00:00Z",
        "event_id": 7036,
        "provider": "Service Control Manager",
        "level": "Information",
        "machine_name": "WIN01",
        "message": "A service changed state",
        "user_id": None,
    }


def bounds():
    return datetime(2026, 10, 17, tzinfo=timezone.utc), datetime(2026, 10, 17, 1, tzinfo=timezone.utc)


def test_system_events_normalize_success_and_filters():
    transport = FakeTransport({"events": [event()], "truncated": True})
    start, end = bounds()

    result = collect_system_events(transport, start_time=start, end_time=end, event_ids=(7036, 7045), max_records=25)

    assert result.event_count == 1
    assert result.truncated is True
    assert result.events[0].time_created.endswith("+00:00")
    assert transport.calls[0]["event_ids"] == (7036, 7045)
    assert transport.calls[0]["max_records"] == 25


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        ("2026-10-17T12:00:00Z", "2026-10-17T12:00:00+00:00"),
        ("2026-10-17T14:51:44.5809165+05:30", "2026-10-17T14:51:44.580916+05:30"),
        ("2026-10-17T14:51:44.5809165Z", "2026-10-17T14:51:44.580916+00:00"),
        ("2026-10-17T17:30:00+05:30", "2026-10-17T17:30:00+05:30"),
        ("/Date(1792238400000)/", "2026-10-17T12:00:00+00:00"),
    ],
)
def test_system_events_accepts_timezone_aware_powerShell_timestamps(timestamp, expected):
    item = event()
    item["time_created"] = timestamp
    transport = FakeTransport({"events": [item], "truncated": False})
    start, end = bounds()

    result = collect_system_events(transport, start_time=start, end_time=end)

    assert result.events[0].time_created == expected


@pytest.mark.parametrize("timestamp", ["2026-10-17T12:00:00", "not-a-timestamp", "/Date(bad)/"])
def test_system_events_rejects_ambiguous_or_invalid_timestamps(timestamp):
    item = event()
    item["time_created"] = timestamp
    transport = FakeTransport({"events": [item], "truncated": False})
    start, end = bounds()

    with pytest.raises(SystemEventError) as exc:
        collect_system_events(transport, start_time=start, end_time=end)

    assert exc.value.category == "malformed"
    assert exc.value.field == "time_created"


@pytest.mark.parametrize(
    ("timestamp", "representation", "format_category"),
    [
        (None, "null", "none"),
        (123, "numeric", "number"),
        ({"DateTime": "hidden"}, "object", "mapping"),
        (["hidden"], "array", "sequence"),
        ("not-a-timestamp", "string", "unknown"),
        ("2026-10-17T12:00:00", "string", "iso_like"),
        ("2026-10-17 12:00:00", "string", "powershell_datetime_like"),
        ("17/10/2026 12:00:00", "string", "locale_datetime_like"),
    ],
)
def test_rejected_timestamp_logs_safe_representation_only(caplog, timestamp, representation, format_category):
    item = event()
    item["time_created"] = timestamp
    transport = FakeTransport({"events": [item], "truncated": False})
    start, end = bounds()

    with caplog.at_level(logging.WARNING, logger="backend.windows_monitoring.events"):
        with pytest.raises(SystemEventError):
            collect_system_events(transport, start_time=start, end_time=end)

    messages = [record.message for record in caplog.records if "timestamp_rejected" in record.message]
    reason = "missing_timezone" if timestamp in ("2026-10-17T12:00:00", "2026-10-17 12:00:00") else "invalid_format"
    assert messages == [
        "windows_system_event_timestamp_rejected field=time_created "
        f"representation={representation} format={format_category} reason={reason}"
        if timestamp is not None and timestamp != ""
        else "windows_system_event_timestamp_rejected field=time_created representation=null format=none reason=missing"
    ]
    assert "hidden" not in messages[0]


def test_system_events_accepts_powerShell_single_event_object():
    transport = FakeTransport({"events": event(), "truncated": False})
    start, end = bounds()

    result = collect_system_events(transport, start_time=start, end_time=end)

    assert result.event_count == 1
    assert result.events[0].record_id == 42


def test_system_events_empty_is_success():
    transport = FakeTransport({"events": [], "truncated": False})
    start, end = bounds()

    result = collect_system_events(transport, start_time=start, end_time=end)

    assert result.events == ()
    assert result.event_count == 0
    assert result.truncated is False


def test_system_events_malformed_output_is_distinct():
    transport = FakeTransport({"unexpected": []})
    start, end = bounds()

    with pytest.raises(SystemEventError) as exc:
        collect_system_events(transport, start_time=start, end_time=end)
    assert exc.value.category == "malformed"


def test_system_events_json_failure_logs_only_parse_metadata(caplog):
    transport = FakeTransport({"events": "not-a-list", "truncated": False})
    start, end = bounds()

    with caplog.at_level(logging.WARNING, logger="backend.windows_monitoring.events"):
        with pytest.raises(SystemEventError) as exc:
            collect_system_events(transport, start_time=start, end_time=end)

    assert exc.value.category == "malformed"
    assert caplog.records[0].message == (
        "windows_system_event_parse_failure stage=event_validation "
        "exception_type=SystemEventError category=malformed field=events reason=not_array"
    )


def test_system_events_validation_failure_logs_only_parse_metadata(caplog):
    invalid = event()
    invalid["record_id"] = "not-an-id"
    transport = FakeTransport({"events": [invalid], "truncated": False})
    start, end = bounds()

    with caplog.at_level(logging.WARNING, logger="backend.windows_monitoring.events"):
        with pytest.raises(SystemEventError) as exc:
            collect_system_events(transport, start_time=start, end_time=end)

    assert exc.value.category == "malformed"
    assert caplog.records[0].message == (
        "windows_system_event_parse_failure stage=event_validation "
        "exception_type=SystemEventError category=malformed field=record_id reason=missing_or_invalid"
    )


def test_system_events_permission_failure_is_distinct():
    transport = FakeTransport({}, stderr=b"Access is denied", status=1)
    start, end = bounds()

    with pytest.raises(SystemEventError) as exc:
        collect_system_events(transport, start_time=start, end_time=end)
    assert exc.value.category == "permission"


def test_system_events_timeout_is_sanitized(monkeypatch):
    class FailingTransport:
        def query_system_events(self, **kwargs):
            raise RuntimeError("secret-value")

    monkeypatch.setattr(WinRMHTTPSAdapter, "_classify", staticmethod(lambda error: SimpleNamespace(category="timeout")))
    start, end = bounds()

    with pytest.raises(SystemEventError) as exc:
        collect_system_events(FailingTransport(), start_time=start, end_time=end)
    assert exc.value.category == "timeout"
    assert "secret-value" not in str(exc.value)


def test_system_events_reject_invalid_ranges_filters_and_limits():
    transport = FakeTransport({"events": [], "truncated": False})
    start, end = bounds()
    with pytest.raises(SystemEventError):
        collect_system_events(transport, start_time=end, end_time=start)
    with pytest.raises(SystemEventError):
        collect_system_events(transport, start_time=start, end_time=end, event_ids=(1, 1))
    with pytest.raises(SystemEventError):
        collect_system_events(transport, start_time=start, end_time=end, max_records=501)
