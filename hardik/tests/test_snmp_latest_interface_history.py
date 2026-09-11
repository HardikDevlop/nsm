from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from backend.database.session import Base
from backend.models.snmp import InterfaceStatistic
from backend.services.snmp_polling import SNMPPoller


def test_latest_previous_history_is_one_query_and_one_row_per_interface():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[InterfaceStatistic.__table__])
    now = datetime(2026, 1, 1, 12, 0, 0)
    with Session(engine) as db:
        db.add_all([
            InterfaceStatistic(id=1, device_id=7, interface_id=11, rx_octets=100, tx_octets=200, created_at=now - timedelta(minutes=2)),
            InterfaceStatistic(id=2, device_id=7, interface_id=11, rx_octets=300, tx_octets=400, created_at=now - timedelta(minutes=1)),
            # Equal timestamp: larger ID must win deterministically.
            InterfaceStatistic(id=3, device_id=7, interface_id=12, rx_octets=500, tx_octets=600, created_at=now),
            InterfaceStatistic(id=4, device_id=7, interface_id=12, rx_octets=700, tx_octets=800, created_at=now),
            InterfaceStatistic(id=5, device_id=8, interface_id=11, rx_octets=999, tx_octets=999, created_at=now + timedelta(minutes=1)),
            InterfaceStatistic(id=6, device_id=7, interface_id=99, rx_octets=999, tx_octets=999, created_at=now + timedelta(minutes=1)),
        ])
        db.commit()

        selects = 0
        def count_selects(_conn, _cursor, statement, _parameters, _context, _executemany):
            nonlocal selects
            if statement.lstrip().upper().startswith("SELECT"):
                selects += 1
        event.listen(engine, "before_cursor_execute", count_selects)
        try:
            rows = SNMPPoller(db)._load_latest_interface_statistics(7, {11, 12})
        finally:
            event.remove(engine, "before_cursor_execute", count_selects)

        assert selects == 1
        assert len(rows) == 2
        by_interface = {row.interface_id: row for row in rows}
        assert by_interface[11].id == 2
        assert by_interface[12].id == 4


def test_first_sample_with_no_history_returns_empty_without_query():
    class NoQuerySession:
        def query(self, *args):
            raise AssertionError("empty identity set must not query")

    assert SNMPPoller(NoQuerySession())._load_latest_interface_statistics(7, set()) == []
