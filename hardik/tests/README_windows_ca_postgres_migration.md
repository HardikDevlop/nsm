# Windows CA migration validation

Run this only from the host terminal, after activating `hardik/.venv`:

```bash
cd /home/agnigate/Desktop/NMS/hardik
source .venv/bin/activate
export TEST_DATABASE_URL='postgresql+psycopg://nms_windows_ca_test:<PASSWORD>@127.0.0.1:5432/nms_test_windows_ca'
pytest -q tests/test_windows_ca_postgres_migration.py
```

Required dependencies are `pytest`, `sqlalchemy`, and `psycopg[binary]`; they
are already listed in the backend requirements. Replace `<PASSWORD>` in the
host shell only—do not commit it or print it.

The test rejects missing, non-PostgreSQL, or non-dedicated URLs; imports models
without starting FastAPI; runs `Base.metadata.create_all()` and then
`run_migrations(engine)`; checks migration tracking, tables, indexes, foreign
keys, checks, and a second idempotent run. It creates no synthetic application
rows, contacts no Windows devices, and performs no cleanup or database drops.

Expected result: `1 passed`; the database contains the schema and migration
records for 0066 and 0067 afterward for manual inspection.
