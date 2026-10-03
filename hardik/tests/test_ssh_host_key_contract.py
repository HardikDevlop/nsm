from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.models import Base, Device, SSHHostKey
from backend.services.remote_access import host_keys
from backend.services.remote_access.host_keys import SSHHostKeyService


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
        trusted = service.trust(item.id, 7)
        assert trusted.id == item.id and trusted.status == "TRUSTED"
        revoked = service.revoke(item.id)
        assert revoked.id == item.id and revoked.status == "REVOKED"
