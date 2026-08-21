from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.config.settings import get_settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    get_settings().database_url,
    pool_pre_ping=True,
    pool_size=20,
    max_overflow=20,
    pool_timeout=10,
    pool_recycle=1800,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def migrate_credential_columns() -> None:
    """Add credential columns introduced after the original database schema.

    ``create_all`` does not alter existing tables, so this idempotent migration
    runs before ORM queries and preserves all existing credential rows.
    """
    required = {
        "snmp_version": "VARCHAR(20)", "community_string": "TEXT",
        "username": "VARCHAR(120)", "password": "TEXT",
        "auth_protocol": "VARCHAR(20)", "auth_password": "TEXT",
        "privacy_protocol": "VARCHAR(20)", "privacy_password": "TEXT",
        "security_level": "VARCHAR(30)", "ssh_port": "INTEGER",
        "api_token": "TEXT",
    }
    with engine.begin() as connection:
        inspector = inspect(connection)
        if "device_credentials" not in inspector.get_table_names():
            return
        present = {column["name"] for column in inspector.get_columns("device_credentials")}
        for name, sql_type in required.items():
            if name not in present:
                connection.execute(text(f'ALTER TABLE device_credentials ADD COLUMN "{name}" {sql_type}'))


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
