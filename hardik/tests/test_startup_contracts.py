from pathlib import Path


MAIN = (Path(__file__).parents[1] / "backend/main.py").read_text(encoding="utf-8")
MIGRATIONS = (Path(__file__).parents[1] / "backend/database/migrations.py").read_text(encoding="utf-8")


def test_startup_mutation_order_precedes_monitoring_restore():
    ordered = [
        "Base.metadata.create_all(bind=engine, tables=existing_tables)",
        "run_migrations(engine)",
        "seed_rbac(db)",
        "seed_ouis_and_products(db)",
        "reconcile_cmdb(db)",
        "get_polling_scheduler()",
        "restore_enabled_servers()",
        "restore_enabled_devices",
    ]
    positions = [MAIN.index(item) for item in ordered]
    assert positions == sorted(positions)


def test_startup_scheduler_failure_has_partial_cleanup_path():
    assert "_cleanup_partial_startup" in MAIN
    assert "partial_startup_flow_receiver_cleanup_failed" in MAIN
    assert "partial_startup_remote_access_cleanup_failed" in MAIN
    assert "partial_startup_scheduler_lease_release_failed" in MAIN
    assert "await _cleanup_partial_startup(flow_ingest=flow_ingest, flow_receiver=flow_receiver)" in MAIN
    assert "syslog_start_failed = True" in MAIN


def test_migration_tracking_records_only_after_handler():
    handler = MIGRATIONS.index("_record_migration(engine, migration)")
    dispatch = MIGRATIONS.index("elif migration.migration_id == \"20261026_0067_windows_ca_bundle_index_reconciliation\":")
    assert dispatch < handler
    assert "ON CONFLICT (migration_id) DO NOTHING" in MIGRATIONS
