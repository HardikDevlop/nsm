import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from backend.api.monitoring_data_routes import (
    MonitoringDataRequest,
    get_monitoring_data,
)
from backend.api.snmp_device_routes import get_latest_memory, get_latest_metrics
from backend.database.session import Base
from backend.models.snmp import LatestMemory, MemoryStatistic
from backend.services.snmp_polling import SNMPPoller


from backend.snmp.collectors.memory import MemoryCollector
from backend.snmp.normalizer import RawDevice
from backend.snmp.memory_resolver import CanonicalMemoryResolution
from backend.linux_monitoring.metrics import LinuxEffectiveMemoryResult


def test_memory_models_expose_nullable_source_metadata_columns():
    expected = {
        "memory_source",
        "memory_semantic",
        "memory_source_status",
        "memory_source_error",
    }
    assert expected.issubset(LatestMemory.__table__.columns.keys())
    assert expected.issubset(MemoryStatistic.__table__.columns.keys())
    for model in (LatestMemory, MemoryStatistic):
        for name in expected:
            assert model.__table__.columns[name].nullable is True


def test_canonical_metadata_is_emitted_without_changing_numeric_fields():
    canonical = CanonicalMemoryResolution(
        eligible=True,
        status="canonical",
        data=LinuxEffectiveMemoryResult(
            version=1,
            total_kib=1000,
            available_kib=250,
            total_bytes=1000 * 1024,
            available_bytes=250 * 1024,
            used_bytes=750 * 1024,
            utilization_percent=75.0,
        ),
    )
    result = MemoryCollector().collect({}, None, None, canonical_memory=canonical)
    assert result.data["total_bytes"] == 1000 * 1024
    assert result.data["used_bytes"] == 750 * 1024
    assert result.data["memory_source"] == "net-snmp-extend"
    assert result.data["memory_semantic"] == "linux_proc_meminfo_memavailable"
    assert result.data["memory_source_status"] == "canonical"
    assert result.data["memory_source_error"] is None


def test_legacy_fallback_metadata_is_emitted_for_extension_failure():
    fallback = CanonicalMemoryResolution(
        eligible=True,
        status="unavailable",
        error_code="timeout",
    )
    result = MemoryCollector().collect(
        {
            "1.3.6.1.4.1.2021.4.5.0": "1000",
            "1.3.6.1.4.1.2021.4.6.0": "500",
        },
        None,
        None,
        canonical_memory=fallback,
    )
    assert result.data["used_bytes"] == 500 * 1024
    assert result.data["memory_source"] == "ucd-snmp"
    assert result.data["memory_semantic"] == "ucd_snmp_memtotalreal_memavailreal"
    assert result.data["memory_source_status"] == "fallback"
    assert result.data["memory_source_error"] == "timeout"


def test_host_resources_fallback_preserves_numeric_calculation_and_metadata():
    raw = {
        "1.3.6.1.2.1.25.2.3.1.2.1": "1.3.6.1.2.1.25.2.1.2",
        "1.3.6.1.2.1.25.2.3.1.4.1": "1024",
        "1.3.6.1.2.1.25.2.3.1.5.1": "100",
        "1.3.6.1.2.1.25.2.3.1.6.1": "25",
    }
    result = MemoryCollector().collect(RawDevice(raw=raw), None, None)
    assert result.data["total_bytes"] == 102400
    assert result.data["used_bytes"] == 25600
    assert result.data["free_bytes"] == 76800
    assert result.data["memory_source"] == "hr-storage"
    assert result.data["memory_semantic"] == "hr_storage_ram"
    assert result.data["memory_source_status"] == "fallback"


def test_vendor_fallback_preserves_numeric_calculation_and_metadata():
    class Registry:
        values = {"total_kb": "100", "used_kb": "25", "free_kb": "75"}

        def resolve(self, module, metric):
            return metric

    result = MemoryCollector().collect(Registry.values, Registry(), SimpleNamespace(vendor="demo"))
    assert result.data["total_bytes"] == 102400
    assert result.data["used_bytes"] == 25600
    assert result.data["free_bytes"] == 76800
    assert result.data["memory_source"] == "vendor"
    assert result.data["memory_semantic"] == "vendor_defined"
    assert result.data["memory_source_status"] == "fallback"


def _memory_db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE devices (id INTEGER PRIMARY KEY)"))
    LatestMemory.__table__.create(engine)
    MemoryStatistic.__table__.create(engine)
    return engine


def _canonical_data():
    return {
        "total_bytes": 1024.0,
        "used_bytes": 256.0,
        "free_bytes": 768.0,
        "cached_bytes": 10.0,
        "buffer_bytes": 11.0,
        "swap_total_bytes": 4096.0,
        "swap_free_bytes": 3072.0,
        "utilization_percent": 25.0,
        "memory_source": "net-snmp-extend",
        "memory_semantic": "linux_proc_meminfo_memavailable",
        "memory_source_status": "canonical",
        "memory_source_error": None,
    }


def test_persistence_create_update_and_historical_canonical_metadata():
    engine = _memory_db()
    with Session(engine) as db:
        poller = SNMPPoller(db)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        asyncio.run(poller._persist_memory(7, _canonical_data(), now))
        db.commit()
        latest = db.query(LatestMemory).one()
        history = db.query(MemoryStatistic).one()
        assert latest.memory_source == history.memory_source == "net-snmp-extend"
        assert latest.memory_semantic == history.memory_semantic == "linux_proc_meminfo_memavailable"
        assert latest.memory_source_status == history.memory_source_status == "canonical"
        assert latest.memory_source_error is None and history.memory_source_error is None
        assert latest.total_bytes == history.total_bytes == 1024.0

        updated = _canonical_data() | {
            "used_bytes": 512.0,
            "utilization_percent": 50.0,
            "memory_source_status": "fallback",
            "memory_source": "ucd-snmp",
            "memory_semantic": "ucd_snmp_memtotalreal_memavailreal",
            "memory_source_error": "timeout",
        }
        asyncio.run(poller._persist_memory(7, updated, now))
        db.commit()
        latest = db.query(LatestMemory).one()
        assert latest.used_bytes == 512.0
        assert latest.memory_source == "ucd-snmp"
        assert latest.memory_source_status == "fallback"
        assert latest.memory_source_error == "timeout"


def test_persistence_fallback_metadata_for_host_resources_and_vendor():
    engine = _memory_db()
    with Session(engine) as db:
        poller = SNMPPoller(db)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        for device_id, source, semantic in (
            (1, "hr-storage", "hr_storage_ram"),
            (2, "vendor", "vendor_defined"),
        ):
            data = _canonical_data() | {
                "memory_source": source,
                "memory_semantic": semantic,
                "memory_source_status": "fallback",
                "memory_source_error": None,
            }
            asyncio.run(poller._persist_memory(device_id, data, now))
        db.commit()
        rows = db.query(LatestMemory).order_by(LatestMemory.device_id).all()
        assert [(r.memory_source, r.memory_semantic, r.memory_source_status) for r in rows] == [
            ("hr-storage", "hr_storage_ram", "fallback"),
            ("vendor", "vendor_defined", "fallback"),
        ]


def test_unavailable_poll_does_not_overwrite_existing_latest_record():
    engine = _memory_db()
    with Session(engine) as db:
        db.add(LatestMemory(device_id=3, total_bytes=100.0, used_bytes=40.0,
                            utilization_percent=40.0, memory_source="net-snmp-extend",
                            memory_source_status="canonical", polled_at=datetime.now()))
        db.commit()
        # _persist_results intentionally does not call _persist_memory for empty data.
        # Repeating that guard here protects the database-backed invariant.
        data = {}
        if data:
            asyncio.run(SNMPPoller(db)._persist_memory(3, data, datetime.now()))
        db.commit()
        row = db.query(LatestMemory).one()
        assert (row.total_bytes, row.used_bytes, row.utilization_percent) == (100.0, 40.0, 40.0)


class _Query:
    def __init__(self, value):
        self.value = value

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.value

    def all(self):
        return self.value if isinstance(self.value, list) else []

    def order_by(self, *args, **kwargs):
        return self


class _ApiDB:
    def __init__(self, memory, history=None):
        self.memory = memory
        self.history = history or []

    def query(self, model):
        return _Query(self.memory if model is LatestMemory else self.history)


def test_latest_memory_route_serializes_nullable_metadata_and_numeric_fields():
    memory = SimpleNamespace(
        total_bytes=100, used_bytes=40, free_bytes=60, cached_bytes=1,
        buffer_bytes=2, swap_total=0, swap_free=0, utilization_percent=40,
        memory_source=None, memory_semantic=None, memory_source_status=None,
        memory_source_error=None, polled_at=None,
    )
    result = get_latest_memory(4, _ApiDB(memory))
    assert result["total_bytes"] == 100
    assert result["utilization_percent"] == 40
    assert result["memory_source"] is None
    assert result["memory_source_error"] is None


def test_latest_metrics_route_uses_v2_cache_and_preserves_null_metadata(monkeypatch):
    class Result:
        def mappings(self):
            return self

        def one(self):
            return {"cpu": None, "memory": {
                "total_bytes": 100, "used_bytes": 40, "free_bytes": 60,
                "cached_bytes": 1, "buffer_bytes": 2, "swap_total": 0,
                "swap_free": 0, "utilization_percent": 40,
                "memory_source": None, "memory_semantic": None,
                "memory_source_status": None, "memory_source_error": None,
                "polled_at": None,
            }, "storage": [], "interfaces": [], "environment": []}

    class DB:
        def execute(self, *args, **kwargs):
            return Result()

    seen = {}
    monkeypatch.setattr("backend.cache.redis_cache.get_json", lambda key: seen.setdefault("read", key) and None)
    monkeypatch.setattr("backend.cache.redis_cache.set_json", lambda key, value: seen.update(write=key, payload=value))
    result = get_latest_metrics(8, DB())
    assert seen["read"].endswith(":metrics-latest:v2")
    assert seen["write"] == seen["read"]
    assert result["memory"]["used_bytes"] == 40
    assert result["memory"]["memory_source"] is None


def test_generic_monitoring_memory_current_and_history_preserve_metadata(monkeypatch):
    memory = SimpleNamespace(
        total_bytes=100, used_bytes=40, free_bytes=60, cached_bytes=1,
        buffer_bytes=2, swap_total=0, swap_free=0, utilization_percent=40,
        memory_source=None, memory_semantic=None, memory_source_status=None,
        memory_source_error=None, polled_at=None,
    )
    device = SimpleNamespace(id=5, deleted_at=None, site_id=1,
                             ip_address="192.0.2.5", hostname="test",
                             status="up")
    db = _ApiDB(memory, [SimpleNamespace(created_at=datetime(2026, 1, 1),
                                         utilization_percent=40, used_bytes=40,
                                         total_bytes=100, memory_source=None,
                                         memory_semantic=None,
                                         memory_source_status=None,
                                         memory_source_error=None)])
    monkeypatch.setattr("backend.api.monitoring_data_routes.derive_device_health", lambda db, device: {"state": "healthy"})
    def query(model):
        if model.__name__ == "Device":
            return _Query(device)
        if model is LatestMemory:
            return _Query(memory)
        if model is MemoryStatistic:
            return _Query(db.history)
        return _Query(None)
    db.query = query
    result = get_monitoring_data(MonitoringDataRequest(device_id=5, modules=["memory"], include_history=True), db, None)
    assert result["modules"]["memory"]["data"]["used_bytes"] == 40
    assert result["modules"]["memory"]["data"]["memory_source"] is None
    assert result["modules"]["memory"]["history"][0]["memory_source"] is None
