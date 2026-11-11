"""Opt-in PostgreSQL API integration checks for Windows Helper security."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import unquote, urlsplit
from uuid import uuid4

import pytest
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from backend.database import migrate_0076, migrate_0077
from backend.windows_monitoring import helper_api, helper_challenge
from backend.windows_monitoring.helper_security import issue_token
from backend.windows_monitoring.models import WindowsHelperCredential, WindowsHelperSubmission

DB = "nms_test_migration_0075"

def _url():
    value = os.getenv("TEST_DATABASE_URL", "").strip()
    if not value:
        pytest.skip("TEST_DATABASE_URL is not set; PostgreSQL API integration is opt-in")
    parsed = urlsplit(value)
    if parsed.scheme not in {"postgresql", "postgresql+psycopg"} or unquote(parsed.path.rsplit("/", 1)[-1]) != DB:
        pytest.fail("TEST_DATABASE_URL must target the verified disposable PostgreSQL instance")
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.port != 55432:
        pytest.fail("TEST_DATABASE_URL must use loopback port 55432")
    if not parsed.username or not parsed.password or parsed.username in {"postgres", "production", "nms", "nms_prod"}:
        pytest.fail("TEST_DATABASE_URL must use explicit non-production credentials")
    return value

def _parents(engine):
    with engine.begin() as c:
        c.execute(text("CREATE TABLE sites (id INTEGER PRIMARY KEY)"))
        c.execute(text("CREATE TABLE vendors (id INTEGER PRIMARY KEY, vendor_name VARCHAR(120) NOT NULL UNIQUE)"))
        c.execute(text("CREATE TABLE device_types (id INTEGER PRIMARY KEY, name VARCHAR(80) NOT NULL UNIQUE)"))
        c.execute(text("""CREATE TABLE devices (
            id INTEGER PRIMARY KEY, site_id INTEGER REFERENCES sites(id), hostname VARCHAR(160) NOT NULL,
            ip_address VARCHAR(45) NOT NULL UNIQUE, mac_address VARCHAR(32),
            vendor_id INTEGER REFERENCES vendors(id), device_type_id INTEGER REFERENCES device_types(id),
            serial_number VARCHAR(120), model VARCHAR(120), firmware_version VARCHAR(120),
            status VARCHAR(30) NOT NULL, monitoring_status BOOLEAN NOT NULL, last_seen TIMESTAMP,
            last_icmp_attempt_at TIMESTAMP, last_icmp_status VARCHAR(20), created_at TIMESTAMP NOT NULL,
            uptime_seconds INTEGER NOT NULL, downtime_seconds INTEGER NOT NULL, last_status_change TIMESTAMP,
            deleted_at TIMESTAMP, topology_metadata JSON)"""))
        c.execute(text("CREATE TABLE schema_migrations (migration_id VARCHAR(255) PRIMARY KEY, description VARCHAR(255) NOT NULL, applied_at TIMESTAMP NOT NULL)"))
        c.execute(text("INSERT INTO sites (id) VALUES (:site_a), (:site_b)"), {"site_a": 1, "site_b": 2})
        c.execute(text("""INSERT INTO devices
            (id, site_id, hostname, ip_address, status, monitoring_status,
             created_at, uptime_seconds, downtime_seconds)
            VALUES
            (:device_a, :site_a, :hostname_a, :ip_a, :status, :monitoring,
             CURRENT_TIMESTAMP, :uptime, :downtime),
            (:device_b, :site_b, :hostname_b, :ip_b, :status, :monitoring,
             CURRENT_TIMESTAMP, :uptime, :downtime)"""), {
                "device_a": 101,
                "device_b": 202,
                "site_a": 1,
                "site_b": 2,
                "hostname_a": "d101",
                "hostname_b": "d202",
                "ip_a": "192.0.2.101",
                "ip_b": "192.0.2.202",
                "status": "unknown",
                "monitoring": True,
                "uptime": 0,
                "downtime": 0,
            })

@pytest.fixture(scope="module")
def db_engine():
    engine = create_engine(_url(), pool_pre_ping=True)
    with engine.connect() as c:
        if c.scalar(text("SELECT current_database()")) != DB:
            pytest.fail("connected database identity mismatch")
        names = {row[0] for row in c.execute(text("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname=current_schema()"))}
        forbidden = {"sites", "devices", "schema_migrations", migrate_0076.CHALLENGE_TABLE, migrate_0077.TABLE}
        if names & forbidden:
            pytest.fail("refusing pre-existing disposable database objects")
    _parents(engine)
    migrate_0076.apply_0076(engine); migrate_0077.apply_0077(engine)
    WindowsHelperCredential.__table__.create(engine); WindowsHelperSubmission.__table__.create(engine)
    try:
        yield engine
    finally:
        with engine.begin() as c:
            for table in ("windows_helper_submissions", "windows_helper_credentials", migrate_0077.TABLE, migrate_0076.CHALLENGE_TABLE, "schema_migrations", "devices", "device_types", "vendors", "sites"):
                c.execute(text(f"DROP TABLE IF EXISTS {table} CASCADE"))
        engine.dispose()

@pytest.fixture
def configured(monkeypatch, db_engine):
    settings = SimpleNamespace(windows_helper_challenge_key_map={"active": b"a" * 32}, windows_helper_challenge_active_key_id="active")
    monkeypatch.setattr(helper_api, "get_settings", lambda: settings)
    monkeypatch.setattr(helper_challenge, "get_settings", lambda: settings)
    return db_engine

def _credential(db):
    token, prefix, digest = issue_token()
    db.add(WindowsHelperCredential(device_id=101, site_id=1, token_prefix=prefix, token_hash=digest, expires_at=datetime.utcnow() + timedelta(minutes=5)))
    db.commit()
    return token

def _collection(db, collection_id, state="COLLECTING"):
    now = datetime.now(timezone.utc)
    db.execute(text("INSERT INTO windows_process_collections (collection_id,device_id,site_id,state,created_at,expires_at,updated_at) VALUES (:id,101,1,:state,:now,:exp,:now)"), {"id": collection_id, "state": state, "now": now, "exp": now + timedelta(minutes=1)})

def test_authenticated_challenge_and_evidence_are_bound_to_device_and_collection(configured):
    with Session(configured) as db:
        token = _credential(db); collection_id = uuid4(); _collection(db, collection_id)
        challenge = helper_challenge.issue_challenge(db, device_id=101, site_id=1, collection_id=collection_id); db.commit()
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        issued = helper_api.get_helper_challenge(101, db, credentials)
        assert issued["collection_id"] == str(collection_id)
        body = helper_api.HelperEvidence(schema_version=1, collection_id=collection_id, collected_at=datetime.now(timezone.utc).isoformat(), session_id=7, challenge=issued["challenge"])
        assert helper_api.submit_helper_evidence(101, body, db, credentials)["accepted"] is True
        with pytest.raises(Exception):
            helper_api.get_helper_challenge(202, db, credentials)

def test_challenge_retrieval_orders_by_persisted_issuance_time(configured):
    with Session(configured) as db:
        token = _credential(db)
        older_id, newer_id = uuid4(), uuid4()
        issued_at = datetime.now(timezone.utc)
        older = helper_challenge.issue_challenge(
            db, device_id=101, site_id=1, collection_id=older_id,
            now=issued_at,
        )
        newer = helper_challenge.issue_challenge(
            db, device_id=101, site_id=1, collection_id=newer_id,
            now=issued_at + timedelta(seconds=2),
        )
        db.commit()
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        result = helper_api.get_helper_challenge(101, db, credentials)
        assert result["collection_id"] == str(newer_id)
        assert result["challenge"] == newer.token
        assert result["challenge"] != older.token

def test_finalized_collection_rejects_signed_evidence(configured):
    with Session(configured) as db:
        token = _credential(db); collection_id = uuid4(); _collection(db, collection_id, "FINALIZED")
        challenge = helper_challenge.issue_challenge(db, device_id=101, site_id=1, collection_id=collection_id); db.commit()
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        body = helper_api.HelperEvidence(schema_version=1, collection_id=collection_id, collected_at=datetime.now(timezone.utc).isoformat(), session_id=7, challenge=challenge.token)
        with pytest.raises(Exception):
            helper_api.submit_helper_evidence(101, body, db, credentials)
