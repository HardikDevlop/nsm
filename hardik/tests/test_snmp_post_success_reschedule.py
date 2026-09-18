from datetime import datetime, timezone
from types import SimpleNamespace

from backend.services.snmp_polling import (
    _build_reschedule_payload,
    _is_restart_restorable_config,
)


def _config():
    return SimpleNamespace(
        id=177,
        device_id=283,
        module_name="system",
        interval_seconds=60,
        enabled=True,
        status="running",
        error_message=None,
        next_poll_at=datetime(2026, 9, 17, 12, 22, tzinfo=timezone.utc),
    )


def test_success_reschedule_payload_carries_original_config_id():
    config = _config()
    payload = _build_reschedule_payload(config)
    assert payload["id"] == 177
    assert payload["config_id"] == 177
    assert payload["device_id"] == 283
    assert payload["module_name"] == "system"


def test_payload_contract_preserves_deterministic_job_identity():
    payload = _build_reschedule_payload(_config())
    assert f'{payload["device_id"]}:{payload["module_name"]}' == "283:system"
    assert payload["id"] == payload["config_id"]


def test_restart_recovery_predicate_is_unchanged():
    assert _is_restart_restorable_config(True, "running")
    assert _is_restart_restorable_config(True, "error")
    assert not _is_restart_restorable_config(True, "not_supported")
