from backend.database import migrate_0077


def test_migration_is_isolated_and_not_registered():
    from backend.database.migrations import MIGRATIONS
    assert migrate_0077.MIGRATION_ID not in {item.migration_id for item in MIGRATIONS}
    assert migrate_0077.TABLE == "windows_process_collections"

