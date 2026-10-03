from types import SimpleNamespace

from backend.services.device_health import derive_monitoring_state
from backend.services.device_health import derive_device_health


def test_enabled_module_is_active_even_when_legacy_icmp_flag_is_false():
    device = SimpleNamespace(id=284, monitoring_status=False)
    config = SimpleNamespace(module_name="interfaces", enabled=True, status="running")

    state = derive_monitoring_state(device, [config])

    assert state["monitoring_enabled"] is True
    assert state["monitoring_state"] == "active"


def test_failed_poll_degrades_without_changing_monitoring_intent():
    device = SimpleNamespace(id=284, monitoring_status=False)
    config = SimpleNamespace(module_name="system", enabled=True, status="error")

    state = derive_monitoring_state(device, [config])

    assert state["monitoring_enabled"] is True
    assert state["monitoring_state"] == "degraded"


def test_explicit_stop_is_stopped():
    device = SimpleNamespace(id=284, monitoring_status=True)
    config = SimpleNamespace(module_name="system", enabled=False, status="stopped")

    state = derive_monitoring_state(device, [config])

    assert state == {
        "monitoring_enabled": False,
        "monitoring_state": "stopped",
        "monitoring_modules": [],
    }


def test_last_seen_is_not_reported_as_icmp_reachable_when_icmp_is_disabled():
    device = SimpleNamespace(
        id=284, monitoring_status=False, last_icmp_attempt_at=None,
        last_icmp_status=None, last_seen=None, status="online",
    )
    health = derive_device_health(_NoQueryDB(), device)
    assert health["icmp_health"]["status"] == "disabled"


class _NoQueryDB:
    def query(self, *_args, **_kwargs):
        return _NoQuery()


class _NoQuery:
    def filter(self, *_args, **_kwargs):
        return self

    def all(self):
        return []
