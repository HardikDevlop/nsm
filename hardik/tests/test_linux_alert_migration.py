from backend.database.migrations import MIGRATIONS


def test_linux_alert_association_migration_preserves_alert_rows_on_server_delete():
    migration = next(item for item in MIGRATIONS if item.migration_id == "20261028_0072_linux_alert_association")
    assert "alerts" in migration.description.lower()

    source = open("hardik/backend/database/migrations.py", encoding="utf-8").read()
    block = source[source.index('migration.migration_id == "20261028_0072_linux_alert_association"'):]
    ddl = block[:block.index("elif migration.migration_id", 1)] if "elif migration.migration_id" in block[1:] else block
    assert "linux_server_id INTEGER REFERENCES linux_servers(id) ON DELETE SET NULL" in ddl
    assert "ON DELETE CASCADE" not in ddl


def test_linux_alert_association_column_is_nullable():
    source = open("hardik/backend/database/migrations.py", encoding="utf-8").read()
    block = source[source.index('migration.migration_id == "20261028_0072_linux_alert_association"'):]
    assert "linux_server_id INTEGER REFERENCES linux_servers(id) ON DELETE SET NULL" in block
    assert "NOT NULL" not in block.split("linux_server_id INTEGER", 1)[1].split("\n", 1)[0]
