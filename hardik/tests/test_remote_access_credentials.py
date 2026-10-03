from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.models import Base, Device, RemoteAccessCredential
from backend.schemas.remote_access import RemoteAccessCredentialRead
from backend.services.remote_access_credentials import (
    RemoteAccessCredentialError,
    RemoteAccessCredentialService,
)
from backend.utils.crypto import encrypt_secret


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[Device.__table__, RemoteAccessCredential.__table__])
    with Session(engine) as session:
        session.add(Device(id=1, hostname="edge-1", ip_address="192.0.2.10", created_at=datetime.utcnow()))
        session.commit()
        yield session
    Base.metadata.drop_all(engine, tables=[RemoteAccessCredential.__table__, Device.__table__])


def make(service, **values):
    return service.create(device_id=1, protocol="ssh", username="admin", secret="unit-secret", **values)


def error(code, fn):
    with pytest.raises(RemoteAccessCredentialError) as exc:
        fn()
    assert exc.value.code == code


def test_protocol_defaults_and_custom_ports(db):
    service = RemoteAccessCredentialService(db)
    assert make(service).port == 22
    assert service.create(device_id=1, protocol="telnet", username="admin", secret="unit-secret").port == 23
    assert service.upsert(device_id=1, protocol="ssh", username="admin", secret="unit-secret", port=2201).port == 2201
    assert service.upsert(device_id=1, protocol="telnet", username="admin", secret="unit-secret", port=2323).port == 2323


@pytest.mark.parametrize("port", [0, 65536, -1])
def test_invalid_ports_rejected(db, port):
    error("INVALID_PORT", lambda: make(RemoteAccessCredentialService(db), port=port))


def test_device_username_and_secret_validation(db):
    service = RemoteAccessCredentialService(db)
    error("DEVICE_NOT_FOUND", lambda: service.create(device_id=404, protocol="ssh", username="u", secret="s"))
    error("INVALID_USERNAME", lambda: service.create(device_id=1, protocol="ssh", username="  ", secret="s"))
    error("SECRET_REQUIRED", lambda: service.create(device_id=1, protocol="ssh", username="u", secret=""))


def test_secret_is_encrypted_and_read_schema_is_secret_free(db):
    service = RemoteAccessCredentialService(db)
    item = make(service)
    assert item.encrypted_secret != "unit-secret"
    assert RemoteAccessCredentialRead.model_validate(item).model_dump().keys() == {
        "id", "device_id", "protocol", "port", "username", "auth_type", "is_verified",
        "last_verified_at", "created_by", "created_at", "updated_at",
    }
    assert "unit-secret" not in repr(RemoteAccessCredentialRead.model_validate(item).model_dump())


def test_upsert_is_unique_and_protocols_coexist(db):
    service = RemoteAccessCredentialService(db)
    first = make(service)
    second = service.upsert(device_id=1, protocol="ssh", username="new", secret="new-secret", port=2022)
    telnet = service.upsert(device_id=1, protocol="telnet", username="t", secret="telnet-secret")
    assert second.id == first.id
    assert len(service.list(device_id=1)) == 2
    assert telnet.protocol == "telnet"


@pytest.mark.parametrize("field,value", [("port", 2200), ("username", "changed"), ("auth_type", "private_key"), ("secret", "changed-secret")])
def test_credential_changes_invalidate_verification(db, field, value):
    service = RemoteAccessCredentialService(db)
    item = make(service)
    service.mark_verified(item.id)
    service.update(item.id, **{field: value})
    assert item.is_verified is False
    assert item.last_verified_at is None


def test_verification_failure_and_internal_resolution(db):
    service = RemoteAccessCredentialService(db)
    item = service.create(device_id=1, protocol="ssh", username="admin", auth_type="private_key", secret="key", port=2200)
    verified = service.mark_verified(item.id)
    assert verified.is_verified and verified.last_verified_at is not None
    failed = service.mark_verification_failed(item.id)
    assert failed.is_verified is False and failed.last_verified_at is None
    resolved = service.resolve_connection_credential(item.id)
    assert (resolved.host, resolved.port, resolved.username, resolved.auth_type, resolved.secret) == ("192.0.2.10", 2200, "admin", "private_key", "key")


def test_not_found_corrupt_secret_and_delete(db):
    service = RemoteAccessCredentialService(db)
    error("CREDENTIAL_NOT_FOUND", lambda: service.resolve_connection_credential(404))
    item = make(service)
    item.encrypted_secret = "corrupt"
    db.flush()
    error("CREDENTIAL_DECRYPTION_FAILED", lambda: service.resolve_connection_credential(item.id))
    other = service.create(device_id=1, protocol="telnet", username="t", secret="s")
    service.delete(item.id)
    assert service.get_by_id(item.id) is None
    assert service.get_by_id(other.id) is not None


def test_concurrent_conflict_path_is_recoverable(db):
    service = RemoteAccessCredentialService(db)
    item = make(service)
    updated = service.upsert(device_id=1, protocol="ssh", username="replacement", secret="replacement-secret")
    assert updated.id == item.id
    assert len(service.list(device_id=1)) == 1
