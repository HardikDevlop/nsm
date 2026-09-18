from types import SimpleNamespace

from backend.api import routes


class _DeviceQuery:
    def __init__(self, devices):
        self.devices = devices

    def filter(self, *_args, **_kwargs):
        return self

    def all(self):
        return self.devices


class _Db:
    def __init__(self, devices):
        self.devices = devices

    def query(self, model):
        return _DeviceQuery(self.devices)


def test_dashboard_health_counts_use_derived_health_not_raw_status(monkeypatch):
    devices = [
        SimpleNamespace(id=1, status="offline"),
        SimpleNamespace(id=2, status="online"),
        SimpleNamespace(id=3, status="online"),
        SimpleNamespace(id=4, status="offline"),
        SimpleNamespace(id=5, status="online"),
    ]
    derived = {
        1: "online",   # raw offline, fresh successful ICMP evidence
        2: "stale",    # raw online, stale monitoring evidence
        3: "degraded",
        4: "unknown",
        5: "offline",
    }
    monkeypatch.setattr(routes, "derive_device_health", lambda _db, device: {"status": derived[device.id]})

    counts = routes._derived_dashboard_health_counts(_Db(devices), devices)

    assert counts == {"online": 1, "offline": 1, "degraded": 1, "stale": 1, "unknown": 1}
    assert sum(counts.values()) == len(devices)


def test_sidebar_has_no_raw_status_health_fallback():
    sidebar = open("figma design/src/components/Sidebar.tsx", encoding="utf-8").read()
    assert "'/snmp/devices?page=1&page_size=200'" not in sidebar
    assert "item.status" not in sidebar
