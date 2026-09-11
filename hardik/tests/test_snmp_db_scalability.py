from __future__ import annotations

from backend.config.settings import Settings
from backend.database.migrations import MIGRATIONS, _ensure_snmp_scalability_indexes
from backend.services import alerting
from backend.services.alerting import NotificationIntent


EXPECTED_INDEX_FRAGMENTS = (
    "ix_cpu_statistics_device_time",
    "ix_memory_statistics_device_time",
    "ix_storage_statistics_device_time",
    "ix_environment_statistics_device_time",
    "ix_interface_statistics_device_interface_time",
    "ix_polling_history_device_collector_time",
    "ix_polling_history_device_id_desc",
    "ix_alerts_active_device_title_status",
)


class _Connection:
    def __init__(self):
        self.statements = []
    def execute(self, statement):
        self.statements.append(str(statement))


class _Begin:
    def __init__(self, connection):
        self.connection = connection
    def __enter__(self):
        return self.connection
    def __exit__(self, *args):
        return False


class _Engine:
    def __init__(self):
        self.connection = _Connection()
    def begin(self):
        return _Begin(self.connection)


def test_snmp_scalability_migration_is_registered_and_idempotent():
    assert any(m.migration_id == "20260910_0045_snmp_scalability_indexes" for m in MIGRATIONS)
    engine = _Engine()
    _ensure_snmp_scalability_indexes(engine)
    sql = "\n".join(engine.connection.statements)
    assert len(engine.connection.statements) == len(EXPECTED_INDEX_FRAGMENTS)
    assert all("CREATE INDEX IF NOT EXISTS" in statement for statement in engine.connection.statements)
    assert all(fragment in sql for fragment in EXPECTED_INDEX_FRAGMENTS)
    assert "device_id, interface_id, created_at DESC, id DESC" in sql
    assert "WHERE deleted_at IS NULL" in sql


def test_snmp_retention_is_disabled_by_default():
    assert Settings(_env_file=None).snmp_history_retention_days == 0


def test_notification_delivery_statuses_use_one_bulk_execute(monkeypatch):
    outcomes = iter([("delivered", "sent-1"), ("failed", None), ("pending", None)])
    monkeypatch.setattr(alerting, "_deliver_intent", lambda _intent: next(outcomes))

    class DB:
        def __init__(self):
            self.calls = []
        def execute(self, statement, parameters):
            self.calls.append((statement, parameters))

    intents = [
        NotificationIntent(index, 10, "title", "body", "warning", "open", f"u{index}@example.com")
        for index in (1, 2, 3)
    ]
    db = DB()
    alerting.deliver_notification_intents(db, intents)
    assert len(db.calls) == 1
    assert db.calls[0][1] == [
        {"id": 1, "status": "delivered", "sent_at": "sent-1"},
        {"id": 2, "status": "failed", "sent_at": None},
        {"id": 3, "status": "pending", "sent_at": None},
    ]
