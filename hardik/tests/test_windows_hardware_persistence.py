from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql

from backend.database.migrations import _ensure_windows_hardware_table
from backend.database.session import Base
from backend.database.migrations import MIGRATIONS
from backend.windows_monitoring.models import WindowsHardwareSnapshot
from backend.windows_monitoring.cim import (
    BIOSResult,
    BaseBoardResult,
    ComputerSystemProductResult,
    ComputerSystemResult,
    HardwareProcessorResult,
    PhysicalMemoryArrayResult,
    PhysicalMemoryResult,
)
from backend.windows_monitoring.persistence import (
    get_hardware_snapshot,
    serialize_hardware_information,
    save_hardware_snapshot,
    upsert_hardware_snapshot,
)


def hardware(processors=None, memory_modules=None):
    return {
        "computer_system": {"manufacturer": "Contoso", "model": "Server X"},
        "system_product": {"vendor": "Contoso", "name": "Server X", "version": None},
        "baseboard": {},
        "bios": {"manufacturer": "Firmware Co", "release_date": None},
        "processors": processors if processors is not None else [{"name": "CPU A"}, {"name": "CPU B"}],
        "memory_modules": memory_modules if memory_modules is not None else [{"capacity_bytes": 1024}, {"capacity_bytes": 2048}],
        "memory_arrays": [],
    }


def fake_db(row_id=41):
    db = Mock()
    db.execute.return_value.scalar_one.return_value = row_id
    db.query.return_value.filter.return_value.one.return_value = SimpleNamespace(
        id=row_id, device_id=314, collected_at=datetime.now(), **hardware()
    )
    return db


def test_hardware_snapshot_model_has_expected_jsonb_columns_and_unique_device_key():
    table = WindowsHardwareSnapshot.__table__
    assert table.name == "windows_hardware_snapshots"
    assert {column.name for column in table.c} == {
        "id", "device_id", "collected_at", "computer_system", "system_product",
        "baseboard", "bios", "processors", "memory_modules", "memory_arrays",
    }
    assert str(table.c.processors.type) == "JSONB"
    assert "uq_windows_hardware_snapshots_device_id" in {constraint.name for constraint in table.constraints}


def test_hardware_snapshot_compiles_postgresql_create_table_ddl_without_nulltype():
    table = WindowsHardwareSnapshot.__table__

    ddl = str(CreateTable(table).compile(dialect=postgresql.dialect()))

    assert "device_id INTEGER NOT NULL" in ddl
    assert "REFERENCES devices (id) ON DELETE CASCADE" in ddl
    assert "JSONB NOT NULL" in ddl
    assert all(column.type.__class__.__name__ != "NullType" for column in table.columns)


def test_actual_hardware_migration_import_path_registers_devices_for_fk_ddl(monkeypatch):
    # This mirrors the migration helper's imports without connecting to a DB.
    class ExistingTableInspector:
        @staticmethod
        def get_table_names():
            return ["windows_hardware_snapshots"]

    monkeypatch.setattr("backend.database.migrations.inspect", lambda _engine: ExistingTableInspector())
    _ensure_windows_hardware_table(object())
    hardware_table = WindowsHardwareSnapshot.__table__
    assert "devices" in Base.metadata.tables

    ddl = str(CreateTable(hardware_table).compile(dialect=postgresql.dialect()))

    assert "device_id INTEGER NOT NULL" in ddl
    assert "FOREIGN KEY(device_id) REFERENCES devices (id) ON DELETE CASCADE" in ddl


def test_insert_and_update_use_device_unique_upsert_and_preserve_arrays():
    db = fake_db()
    row = upsert_hardware_snapshot(db, 314, hardware())
    statement = db.execute.call_args.args[0]
    params = statement.compile().params

    assert row.id == 41
    assert statement.table.name == "windows_hardware_snapshots"
    assert statement._post_values_clause is not None
    assert params["device_id"] == 314
    assert len(params["processors"]) == 2
    assert len(params["memory_modules"]) == 2
    assert {column.name for column in statement.table.constraints} >= {"uq_windows_hardware_snapshots_device_id"}


def test_multiple_devices_are_independent_by_device_conflict_key():
    first = fake_db()
    second = fake_db(row_id=42)
    upsert_hardware_snapshot(first, 314, hardware())
    upsert_hardware_snapshot(second, 315, hardware(processors=[]))

    first_params = first.execute.call_args.args[0].compile().params
    second_params = second.execute.call_args.args[0].compile().params
    assert first_params["device_id"] == 314
    assert second_params["device_id"] == 315
    assert second_params["processors"] == []


def test_null_and_empty_values_are_preserved_without_fabrication():
    value = serialize_hardware_information(hardware(processors=[], memory_modules=[{"capacity_bytes": None, "manufacturer": None}]))

    assert value["baseboard"] == {}
    assert value["processors"] == []
    assert value["memory_modules"] == [{"capacity_bytes": None, "manufacturer": None}]
    assert value["system_product"]["version"] is None


def test_serializer_normalizes_cim_singleton_lists_and_preserves_arrays():
    value = serialize_hardware_information({
        "computer_system": [{"model": "Server X"}],
        "system_product": [{"name": "Product X"}],
        "baseboard": [],
        "bios": None,
        "processors": [{"name": "CPU A"}, {"name": "CPU B"}],
        "memory_modules": [{"capacity_bytes": 1024}],
        "memory_arrays": None,
    })

    assert value["computer_system"] == {"model": "Server X"}
    assert value["system_product"] == {"name": "Product X"}
    assert value["baseboard"] == {}
    assert value["bios"] == {}
    assert len(value["processors"]) == 2
    assert len(value["memory_modules"]) == 1
    assert value["memory_arrays"] == []


def test_real_cim_dataclass_singletons_survive_serialization_and_upsert():
    cim_value = {
        "computer_system": [ComputerSystemResult("Dell Inc.", "Latitude 3420", "x64-based PC", "WORKGROUP", "WORKGROUP", False, 1, 8)],
        "system_product": [ComputerSystemProductResult("Dell Inc.", "Latitude 3420", "1.0")],
        "baseboard": [BaseBoardResult("Dell Inc.", "0T6K7V", "A00")],
        "bios": [BIOSResult("Dell Inc.", "1.24.0", "2024-01-01T00:00:00+00:00")],
        "processors": [HardwareProcessorResult("11th Gen Intel", "Intel", 4, 8, 4200)],
        "memory_modules": [PhysicalMemoryResult(8 * 1024**3, 3200, "Samsung", 26, "DIMM 1", "BANK 0")],
        "memory_arrays": [PhysicalMemoryArrayResult(32 * 1024**3, 2, "System Board", 3)],
    }

    serialized = serialize_hardware_information(cim_value)
    db = fake_db()
    upsert_hardware_snapshot(db, 314, cim_value)
    params = db.execute.call_args.args[0].compile().params

    assert serialized["computer_system"]["model"] == "Latitude 3420"
    assert serialized["system_product"]["vendor"] == "Dell Inc."
    assert serialized["baseboard"]["product"] == "0T6K7V"
    assert serialized["bios"]["smbios_bios_version"] == "1.24.0"
    assert params["computer_system"]["manufacturer"] == "Dell Inc."
    assert len(params["processors"]) == 1
    assert params["memory_modules"][0]["capacity_bytes"] == 8 * 1024**3


def test_get_hardware_snapshot_is_device_scoped():
    db = Mock()
    expected = SimpleNamespace(device_id=314)
    db.scalars.return_value.first.return_value = expected

    assert get_hardware_snapshot(db, 314) is expected
    db.scalars.assert_called_once()


def test_failed_write_rolls_back_without_commit():
    db = fake_db()
    db.execute.side_effect = RuntimeError("database unavailable")

    with pytest.raises(RuntimeError):
        save_hardware_snapshot(db, 314, hardware())

    db.rollback.assert_called_once()
    db.commit.assert_not_called()


def test_hardware_migration_is_registered_once_with_expected_id():
    ids = [migration.migration_id for migration in MIGRATIONS]

    assert ids.count("20261017_0065_windows_hardware_snapshots") == 1
    assert ids.index("20261017_0065_windows_hardware_snapshots") > ids.index("20261017_0064_windows_event_logs")
