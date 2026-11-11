from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.windows_monitoring import helper_challenge as service


KEY = b"k" * 32
NOW = datetime(2026, 11, 4, 12, 0, tzinfo=timezone.utc)


class Settings:
    windows_helper_challenge_key_map = {"active": KEY, "previous": b"p" * 32}
    windows_helper_challenge_active_key_id = "active"


class Query:
    def __init__(self, row): self.row = row
    def filter(self, *_expressions): return self
    def first(self): return self.row


class DB:
    def __init__(self, row=None):
        self.row = row
        self.added = []
        self.statement = None
    def get(self, _model, _ident): return SimpleNamespace(id=101, site_id=7)
    def add(self, row): self.added.append(row)
    def flush(self): return None
    def query(self, _model): return Query(self.row)
    def execute(self, statement):
        self.statement = statement
        return SimpleNamespace(first=lambda: None, rowcount=0)


def _issue(monkeypatch):
    monkeypatch.setattr(service, "get_settings", lambda: Settings())
    db = DB()
    result = service.issue_challenge(db, device_id=101, collection_id=uuid4(), now=NOW)
    return db, result


def test_issue_and_verify_challenge(monkeypatch):
    db, issued = _issue(monkeypatch)
    db.row = db.added[0]
    verified = service.verify_challenge(db, issued.token, device_id=101, site_id=7, collection_id=issued.collection_id, now=NOW)
    assert verified.challenge_id == issued.challenge_id
    assert db.added[0].nonce_hash != issued.token


@pytest.mark.parametrize("kwargs", [
    {"device_id": 102},
    {"site_id": 8},
    {"collection_id": uuid4()},
    {"purpose": "other"},
])
def test_wrong_binding_is_rejected(monkeypatch, kwargs):
    db, issued = _issue(monkeypatch)
    db.row = db.added[0]
    values = {"device_id": 101, "site_id": 7, "collection_id": issued.collection_id}
    values.update(kwargs)
    with pytest.raises(service.ChallengeError):
        service.verify_challenge(db, issued.token, **values, now=NOW)


def test_tampering_unknown_key_and_previous_key_are_rejected_or_supported(monkeypatch):
    db, issued = _issue(monkeypatch)
    db.row = db.added[0]
    with pytest.raises(service.ChallengeError):
        service.verify_challenge(db, issued.token[:-1] + ("x" if issued.token[-1] != "x" else "y"), device_id=101, site_id=7, collection_id=issued.collection_id, now=NOW)

    monkeypatch.setattr(service, "get_settings", lambda: SimpleNamespace(windows_helper_challenge_key_map={"previous": Settings.windows_helper_challenge_key_map["previous"]}, windows_helper_challenge_active_key_id="previous"))
    # A token signed with a retained previous key remains verifiable after rotation.
    rotated = service.jwt.encode({
        "typ": service.TOKEN_TYPE, "ver": service.TOKEN_VERSION, "jti": str(issued.challenge_id),
        "device_id": 101, "site_id": 7, "collection_id": str(issued.collection_id),
        "purpose": service.DEFAULT_PURPOSE, "iat": int(NOW.timestamp()), "exp": int((NOW + timedelta(seconds=30)).timestamp()), "nonce": str(issued.challenge_id),
    }, Settings.windows_helper_challenge_key_map["previous"], algorithm=service.ALGORITHM, headers={"kid": "previous", "typ": service.TOKEN_TYPE})
    db.row.nonce_hash = service._hash_nonce(str(issued.challenge_id))
    db.row.issued_at = NOW
    db.row.expires_at = NOW + timedelta(seconds=30)
    assert service.verify_challenge(db, rotated, device_id=101, site_id=7, collection_id=issued.collection_id, now=NOW).challenge_id == issued.challenge_id


@pytest.mark.parametrize("when", [NOW - timedelta(seconds=31), NOW + timedelta(seconds=31)])
def test_expired_or_future_token_is_rejected(monkeypatch, when):
    db, issued = _issue(monkeypatch)
    db.row = db.added[0]
    with pytest.raises(service.ChallengeError):
        service.verify_challenge(db, issued.token, device_id=101, site_id=7, collection_id=issued.collection_id, now=when)


def test_disabled_signing_and_invalid_issue_request_fail_closed(monkeypatch):
    monkeypatch.setattr(service, "get_settings", lambda: SimpleNamespace(windows_helper_challenge_key_map={}, windows_helper_challenge_active_key_id=""))
    with pytest.raises(service.ChallengeError):
        service.issue_challenge(DB(), device_id=101, collection_id=uuid4(), now=NOW)


def test_consume_is_conditional_and_cancellation_never_overwrites_consumed(monkeypatch):
    db, issued = _issue(monkeypatch)
    db.execute = lambda statement: SimpleNamespace(first=lambda: None, rowcount=0)
    db.row = db.added[0]
    with pytest.raises(service.ChallengeError):
        service.consume_challenge(db, issued.token, device_id=101, site_id=7, collection_id=issued.collection_id, now=NOW)
    assert service.cancel_challenge(db, issued.challenge_id, now=NOW) is False
