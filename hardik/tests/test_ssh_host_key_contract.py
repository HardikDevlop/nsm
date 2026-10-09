from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.models import Base, Device, SSHHostKey
from backend.services.remote_access import host_keys
from backend.services.remote_access.host_keys import SSHHostKeyService
from backend.api import remote_access_routes
from backend.api.remote_access_routes import _should_commit_test_result


def test_unknown_host_key_result_is_commit_eligible_but_other_failures_are_not():
    assert _should_commit_test_result({"success": False, "error_code": "HOST_KEY_UNKNOWN", "host_key_id": 1})
    assert not _should_commit_test_result({"success": False, "error_code": "SSH_AUTH_FAILED"})
    assert not _should_commit_test_result({"success": False, "error_code": "SSH_HANDSHAKE_FAILED"})
    assert not _should_commit_test_result({"success": False, "error_code": "INTERNAL_ERROR"})


def test_trust_endpoint_loads_persisted_key_and_marks_it_trusted(monkeypatch):
    from backend.api.remote_access_routes import trust_ssh_host_key
    from backend.models import User
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[Device.__table__, SSHHostKey.__table__])
    with Session(engine) as db:
        db.add(Device(id=1, hostname="edge-1", ip_address="192.0.2.10", created_at=datetime.utcnow()))
        db.flush()
        item = SSHHostKey(device_id=1, host="192.0.2.10", port=22, key_type="ssh-rsa",
                          public_host_key="cHVibGlj", fingerprint="SHA256:test", status="PENDING")
        db.add(item); db.commit()
        monkeypatch.setattr(remote_access_routes, "get_user_permission_codes", lambda _user: {"remote_access:manage_credentials"})
        monkeypatch.setattr(remote_access_routes, "can_access_site", lambda _user, _site: True)
        trusted = trust_ssh_host_key(item.id, db=db, current_user=User(id=7))
        assert trusted["id"] == item.id and trusted["status"] == "TRUSTED"


def test_scan_trust_revoke_preserves_safe_contract(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine, tables=[Device.__table__, SSHHostKey.__table__])
    with Session(engine) as db:
        db.add(Device(id=1, hostname="edge-1", ip_address="192.0.2.10", created_at=datetime.utcnow()))
        db.commit()
        monkeypatch.setattr(host_keys, "fetch_host_key", lambda *args: ("ssh-ed25519", "cHVibGlj", "SHA256:abc"))
        service = SSHHostKeyService(db)
        item = service.scan(1, 22)
        assert item.id and item.status == "PENDING"
        assert not hasattr(item, "private_key")
        pending_id = item.id
        db.commit()  # request 1 ends after persisting the reviewable key
    with Session(engine) as next_request:
        persisted = next_request.get(SSHHostKey, pending_id)
        assert persisted is not None and persisted.status == "PENDING"
        service = SSHHostKeyService(next_request)
        trusted = service.trust(pending_id, 7)
        next_request.commit()  # request 2 trusts the same returned ID
        assert trusted.id == pending_id and trusted.status == "TRUSTED"
        assert next_request.get(SSHHostKey, pending_id).status == "TRUSTED"
    with Session(engine) as verify:
        assert verify.get(SSHHostKey, pending_id).status == "TRUSTED"
