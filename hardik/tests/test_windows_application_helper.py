from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend.windows_monitoring.application_helper import classify_process_metadata, classify_visible_processes, validate_helper_payload


def payload(**overrides):
    value = {
        "schema_version": 1,
        "collected_at": "2026-11-03T12:00:00+00:00",
        "session_id": 1,
        "visible_process_ids": [10, 10, 11],
    }
    value.update(overrides)
    return value


def test_payload_is_normalized_and_process_ids_are_deduplicated():
    result = validate_helper_payload(payload(), now=datetime(2026, 11, 3, 12, 0, 1, tzinfo=timezone.utc))
    assert result["visible_process_ids"] == [10, 11]


def test_metadata_classification_requires_executable_path_and_never_uses_name_only():
    assert classify_process_metadata(SimpleNamespace(name="explorer.exe", executable_path=None)) == (None, None)
    assert classify_process_metadata(SimpleNamespace(executable_path=r"C:\Windows\System32\svchost.exe"))[0] == "windows"
    assert classify_process_metadata(SimpleNamespace(executable_path=r"C:\Users\User\app.exe"))[0] == "background"


@pytest.mark.parametrize("bad", [
    {"schema_version": 2},
    {"session_id": -1},
    {"visible_process_ids": [0]},
    {"visible_process_ids": ["10"]},
])
def test_invalid_payloads_are_rejected(bad):
    value = payload(**bad)
    with pytest.raises(ValueError):
        validate_helper_payload(value, now=datetime(2026, 11, 3, 12, 0, 1, tzinfo=timezone.utc))


def test_stale_payload_is_rejected():
    with pytest.raises(ValueError, match="stale"):
        validate_helper_payload(payload(), now=datetime(2026, 11, 3, 12, 1, tzinfo=timezone.utc))


def test_visible_process_requires_session_and_creation_identity():
    rows = (
        SimpleNamespace(process_id=10, session_id=1, creation_time="new"),
        SimpleNamespace(process_id=11, session_id=2, creation_time="same-exe"),
        SimpleNamespace(process_id=12, session_id=1, creation_time="missing-proof"),
    )
    evidence = payload(process_creation_times={"10": "new", "11": "same-exe"})
    result = classify_visible_processes(rows, evidence, now=datetime(2026, 11, 3, 12, 0, 1, tzinfo=timezone.utc))
    assert result[0].classification == "app"
    assert getattr(result[1], "classification", None) is None
    assert getattr(result[2], "classification", None) is None


def test_pid_reuse_without_creation_proof_stays_unknown():
    row = SimpleNamespace(process_id=10, session_id=1, creation_time="reused")
    result = classify_visible_processes((row,), payload(), now=datetime(2026, 11, 3, 12, 0, 1, tzinfo=timezone.utc))
    assert getattr(result[0], "classification", None) is None
