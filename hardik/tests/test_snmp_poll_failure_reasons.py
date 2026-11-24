import asyncio
from datetime import datetime
from types import SimpleNamespace

from backend.services.snmp_polling import SNMPPoller, _sanitize_poll_reason


def test_known_memory_failure_reason_is_preserved_and_bounded():
    reason = (
        "No memory OID responded: tried UCD-SNMP (1.3.6.1.4.1.2021.4.x), "
        "hrStorageTable (1.3.6.1.2.1.25.2.3.1), and vendor profile OIDs"
    )
    assert _sanitize_poll_reason(reason) == reason
    assert len(_sanitize_poll_reason("x" * 800)) == 500


def test_missing_or_sensitive_reason_uses_compatibility_fallback():
    assert _sanitize_poll_reason(None) == "Module not supported"
    assert _sanitize_poll_reason("Traceback (most recent call last): secret=password") == "Module not supported"
    assert _sanitize_poll_reason("") == "Module not supported"


def test_persist_history_preserves_reason_and_status():
    class DB:
        def __init__(self):
            self.items = []

        def add(self, item):
            self.items.append(item)

    db = DB()
    asyncio.run(SNMPPoller(db)._persist_history(
        359,
        "memory",
        {},
        False,
        datetime(2026, 11, 23),
        reason="No memory OID responded: tried UCD-SNMP and hrStorageTable",
    ))
    assert db.items[0].status == "not_supported"
    assert db.items[0].error == "No memory OID responded: tried UCD-SNMP and hrStorageTable"


def test_persist_history_keeps_success_error_null():
    class DB:
        def __init__(self):
            self.items = []

        def add(self, item):
            self.items.append(item)

    db = DB()
    asyncio.run(SNMPPoller(db)._persist_history(
        359, "memory", {"total_bytes": 1}, True, datetime(2026, 11, 23),
        reason="ignored on success",
    ))
    assert db.items[0].status == "success"
    assert db.items[0].error is None
