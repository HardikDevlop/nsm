import asyncio
from datetime import datetime

from backend.models import Interface
from backend.models.snmp import InterfaceStatistic, LatestInterface
from backend.services.snmp_polling import SNMPPoller


class _Query:
    def __init__(self, db, model):
        self.db = db
        self.model = model

    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def all(self):
        self.db.query_all_calls[self.model] = self.db.query_all_calls.get(self.model, 0) + 1
        return []


class _BatchReadSession:
    def __init__(self):
        self.query_all_calls = {}
        self.added = []

    def query(self, model):
        return _Query(self, model)

    def add(self, value):
        self.added.append(value)

    def flush(self):
        for index, value in enumerate(self.added, start=1):
            if isinstance(value, Interface) and value.id is None:
                value.id = index


def test_interface_discovery_persistence_uses_batch_reads():
    db = _BatchReadSession()
    poller = SNMPPoller(db)
    now = datetime(2026, 8, 29, 10, 0, 0)
    data = {
        "interfaces": [
            {"ifIndex": 1, "name": "eth0", "oper_status": "up", "speed_bps": 1_000_000_000},
            {"ifIndex": 2, "name": "eth1", "oper_status": "down", "speed_bps": 100_000_000},
        ]
    }

    asyncio.run(poller._persist_interfaces(7, data, now))

    assert db.query_all_calls == {
        Interface: 1,
        InterfaceStatistic: 1,
        LatestInterface: 1,
    }
    persisted_interfaces = [item for item in db.added if isinstance(item, Interface)]
    assert sorted(item.interface_name for item in persisted_interfaces) == ["eth0", "eth1"]
