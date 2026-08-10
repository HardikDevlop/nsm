"""One-shot helper: creates the NMS_DB database (if missing) and all tables."""

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

from backend.config.settings import get_settings


def create_database_if_missing() -> None:
    url = make_url(get_settings().database_url)
    db_name = url.database
    with psycopg.connect(
        host=url.host or "localhost",
        port=url.port or 5432,
        user=url.username,
        password=url.password,
        dbname="postgres",
        autocommit=True,
    ) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (db_name,)
        ).fetchone()
        if exists:
            print(f"Database {db_name} already exists")
        else:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
            print(f"Database {db_name} created")


def create_tables_and_seed() -> None:
    from backend.database.session import Base, SessionLocal, engine, migrate_credential_columns
    from backend.seed import seed_rbac
    import backend.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    migrate_credential_columns()
    print(f"Tables created: {', '.join(sorted(Base.metadata.tables))}")
    with SessionLocal() as db:
        seed_rbac(db)
    print("RBAC seed complete (roles: Admin/Operator/Viewer, user: admin@gmail.com)")


if __name__ == "__main__":
    create_database_if_missing()
    create_tables_and_seed()
