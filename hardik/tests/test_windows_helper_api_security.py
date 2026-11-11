"""HTTP-level security tests for the Windows Helper API.

The app contains only the helper router and uses an in-memory fake session.
There is deliberately no TEST_DATABASE_URL fallback and no database engine in
this module, so importing or running these tests cannot connect to production.
"""
from __future__ import annotations

import json
import anyio
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from sqlalchemy.sql.elements import False_, Null, True_
from sqlalchemy.exc import IntegrityError

from backend.dependencies import get_current_user
from backend.database.session import get_db
from backend.models import Device
from backend.windows_monitoring import helper_api
from backend.windows_monitoring.helper_security import issue_token
from backend.windows_monitoring.models import WindowsHelperCredential, WindowsHelperSubmission


class FakeQuery:
    def __init__(self, db, model):
        self.db = db
        self.model = getattr(model, "class_", model)
        self.rows = list(db.rows_for(self.model))

    def filter(self, *expressions):
        self.rows = [row for row in self.rows if all(self._matches(row, expression) for expression in expressions)]
        return self

    def with_for_update(self):
        return self

    def order_by(self, *_expressions):
        return self

    def limit(self, count):
        self.rows = self.rows[:count]
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        if self.model is WindowsHelperSubmission:
            return [SimpleNamespace(id=row.id) for row in self.rows]
        return list(self.rows)

    def delete(self, synchronize_session=False):
        del synchronize_session
        for row in self.rows:
            self.db.submissions.remove(row)
        return len(self.rows)

    @staticmethod
    def _matches(row, expression):
        left = getattr(expression, "left", None)
        right = getattr(expression, "right", None)
        key = getattr(left, "key", None)
        value = getattr(right, "value", None)
        operator = getattr(getattr(expression, "operator", None), "__name__", "")
        current = getattr(row, key, None)
        if operator == "is_":
            if isinstance(right, True_):
                return current is True
            if isinstance(right, False_):
                return current is False
            if isinstance(right, Null):
                return current is None
            return current is value
        if operator == "eq":
            return current == value
        if operator in {"le", "lt"}:
            return current <= value if operator == "le" else current < value
        if operator in {"in_op", "in_"}:
            return current in value
        raise AssertionError(f"unsupported test query expression: {expression!r}")


class FakeSession:
    def __init__(self, devices, *, audits):
        self.devices = devices
        self.credentials = []
        self.submissions = []
        self.audits = audits
        self.next_id = 1

    def get(self, model, ident):
        if model is Device:
            return self.devices.get(ident)
        if model is WindowsHelperCredential:
            return next((row for row in self.credentials if row.id == ident), None)
        return None

    def query(self, model):
        return FakeQuery(self, model)

    def rows_for(self, model):
        if model is WindowsHelperCredential:
            return self.credentials
        if model is WindowsHelperSubmission:
            return self.submissions
        return []

    def add(self, row):
        if getattr(row, "id", None) is None:
            row.id = self.next_id
            self.next_id += 1
        if isinstance(row, WindowsHelperCredential):
            self.credentials.append(row)
        elif isinstance(row, WindowsHelperSubmission):
            self.submissions.append(row)
        else:
            self.audits.append(row)

    def commit(self):
        collection_ids = [row.collection_id for row in self.submissions]
        if len(collection_ids) != len(set(collection_ids)):
            duplicate = self.submissions.pop()
            raise IntegrityError(
                "duplicate collection_id",
                {"collection_id": duplicate.collection_id},
                Exception("uq_windows_helper_submission_collection"),
            )
        return None

    def refresh(self, _row):
        return None

    def rollback(self):
        return None


class LocalHTTPClient:
    """Synchronous facade over a direct, bounded ASGI request."""

    def __init__(self, app):
        self.app = app

    def post(self, url, **kwargs):
        async def request():
            body = json.dumps(kwargs["json"]).encode() if "json" in kwargs else b""
            headers = [(b"content-length", str(len(body)).encode())]
            if body:
                headers.insert(0, (b"content-type", b"application/json"))
            for key, value in kwargs.get("headers", {}).items():
                headers.append((key.lower().encode(), value.encode()))
            path = url.split("?", 1)[0]
            response = {"status": None, "headers": [], "body": bytearray()}
            sent = False

            async def receive():
                nonlocal sent
                if sent:
                    return {"type": "http.disconnect"}
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}

            async def send(message):
                if message["type"] == "http.response.start":
                    response["status"] = message["status"]
                    response["headers"] = message["headers"]
                elif message["type"] == "http.response.body":
                    response["body"].extend(message.get("body", b""))

            with anyio.fail_after(5):
                await self.app({
                    "type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
                    "http_version": "1.1", "method": "POST", "scheme": "http",
                    "path": path, "raw_path": path.encode(), "query_string": b"",
                    "headers": headers, "client": ("testclient", 50000), "server": ("testserver", 80),
                }, receive, send)
            return response

        result = anyio.run(request)

        class Response:
            status_code = result["status"]

            def json(self):
                return json.loads(result["body"])

            @property
            def text(self):
                return result["body"].decode()

        return Response()


def _user(user_id, *permissions, site_ids=(1,)):
    return SimpleNamespace(
        id=user_id,
        email=f"user-{user_id}@example.invalid",
        status="active",
        sites=[SimpleNamespace(id=site_id) for site_id in site_ids],
        role=SimpleNamespace(
            role_name="Operator",
            permissions=[SimpleNamespace(code=permission) for permission in permissions],
        ),
    )


@pytest.fixture
def security_app(monkeypatch):
    sites = {1: SimpleNamespace(id=1), 2: SimpleNamespace(id=2)}
    devices = {
        101: Device(id=101, site_id=1),
        202: Device(id=202, site_id=2),
    }
    audits = []
    db = FakeSession(devices, audits=audits)
    current_user = {"value": _user(7, "windows_helper:manage", site_ids=(1,))}
    app = FastAPI()
    app.include_router(helper_api.router)
    async def run_in_test_executor(func, *args, **kwargs):
        return func(*args, **kwargs)

    import fastapi.dependencies.utils as dependency_utils
    import fastapi.routing as routing
    import starlette.concurrency as concurrency
    monkeypatch.setattr(dependency_utils, "run_in_threadpool", run_in_test_executor)
    monkeypatch.setattr(routing, "run_in_threadpool", run_in_test_executor)
    monkeypatch.setattr(concurrency, "run_in_threadpool", run_in_test_executor)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: current_user["value"]

    def capture_audit(*args, **kwargs):
        audits.append((args, kwargs))

    monkeypatch.setattr(helper_api, "record_audit_event", capture_audit)
    yield SimpleNamespace(client=LocalHTTPClient(app), db=db, user=current_user, devices=devices, sites=sites, audits=audits)
    app.dependency_overrides.clear()


def _issue(fixture, device_id=101, days=30):
    response = fixture.client.post("/windows/helper/credentials", json={"device_id": device_id, "expires_in_days": days})
    assert response.status_code == 201
    return response.json()


def _credential(fixture, device_id=101, *, expires_at=None, active=True):
    token, prefix, digest = issue_token()
    row = WindowsHelperCredential(
        id=len(fixture.db.credentials) + 1,
        device_id=device_id,
        site_id=fixture.devices[device_id].site_id,
        token_prefix=prefix,
        token_hash=digest,
        expires_at=expires_at or datetime.utcnow() + timedelta(days=1),
        is_active=active,
        revoked_at=None if active else datetime.utcnow(),
    )
    fixture.db.credentials.append(row)
    return row, token


def _evidence(collection_id=None, device_session=1):
    return {
        "schema_version": 1,
        "collection_id": str(collection_id or uuid4()),
        "collected_at": datetime.utcnow().isoformat() + "+00:00",
        "session_id": device_session,
        "visible_process_ids": [10],
        "process_creation_times": {"10": "2026-11-03T12:00:00+00:00"},
    }


def test_authorized_issuance_returns_one_time_token_and_audits(security_app):
    result = _issue(security_app)
    assert result["token"]
    assert result["token_prefix"] == result["token"][:12]
    assert result["token"] not in security_app.db.credentials[0].token_hash
    assert security_app.audits[0][1]["action"] == "ISSUE"


def test_issuance_requires_manage_permission(security_app):
    security_app.user["value"] = _user(8, site_ids=(1,))
    response = security_app.client.post("/windows/helper/credentials", json={"device_id": 101})
    assert response.status_code == 403


def test_cross_site_issuance_is_denied(security_app):
    response = security_app.client.post("/windows/helper/credentials", json={"device_id": 202})
    assert response.status_code == 404


def test_revoke_and_rotate_require_site_authorization(security_app):
    issued = _issue(security_app)
    security_app.user["value"] = _user(8, "windows_helper:manage", site_ids=(2,))
    assert security_app.client.post(f"/windows/helper/credentials/{issued['id']}/revoke").status_code == 404
    assert security_app.client.post(f"/windows/helper/credentials/{issued['id']}/rotate").status_code == 404
    security_app.user["value"] = _user(7, "windows_helper:manage", site_ids=(1,))
    assert security_app.client.post(f"/windows/helper/credentials/{issued['id']}/revoke").status_code == 200


def test_valid_invalid_expired_and_revoked_tokens(security_app):
    row, token = _credential(security_app)
    assert helper_api._auth(security_app.db, SimpleNamespace(scheme="Bearer", credentials=token)) is row
    for credentials in (SimpleNamespace(scheme="Basic", credentials=token), SimpleNamespace(scheme="Bearer", credentials="bad")):
        with pytest.raises(helper_api.HTTPException) as error:
            helper_api._auth(security_app.db, credentials)
        assert error.value.status_code == 401
    row.expires_at = datetime.utcnow() - timedelta(seconds=1)
    with pytest.raises(helper_api.HTTPException) as expired:
        helper_api._auth(security_app.db, SimpleNamespace(scheme="Bearer", credentials=token))
    assert expired.value.status_code == 401
    row.expires_at = datetime.utcnow() + timedelta(days=1)
    row.is_active = False
    row.revoked_at = datetime.utcnow()
    with pytest.raises(helper_api.HTTPException) as revoked:
        helper_api._auth(security_app.db, SimpleNamespace(scheme="Bearer", credentials=token))
    assert revoked.value.status_code == 401


def test_fake_query_preserves_sql_boolean_and_null_identity_semantics():
    row = SimpleNamespace(is_active=True, revoked_at=None)
    assert FakeQuery._matches(row, WindowsHelperCredential.is_active.is_(True)) is True
    assert FakeQuery._matches(row, WindowsHelperCredential.is_active.is_(False)) is False
    assert FakeQuery._matches(row, WindowsHelperCredential.revoked_at.is_(None)) is True


def test_cross_device_and_cross_site_evidence_are_denied(security_app):
    row, token = _credential(security_app, 101)
    headers = {"Authorization": f"Bearer {token}"}
    assert security_app.client.post("/windows/helper/devices/202/evidence", json=_evidence(), headers=headers).status_code == 403
    security_app.devices[101].site_id = 2
    assert security_app.client.post("/windows/helper/devices/101/evidence", json=_evidence(), headers=headers).status_code == 403
    assert row.last_used_at is None


def test_duplicate_collection_id_returns_409_and_success_updates_last_used(security_app):
    row, token = _credential(security_app)
    headers = {"Authorization": f"Bearer {token}"}
    payload = _evidence()
    first = security_app.client.post("/windows/helper/devices/101/evidence", json=payload, headers=headers)
    assert first.status_code == 202
    assert row.last_used_at is not None
    duplicate = security_app.client.post("/windows/helper/devices/101/evidence", json=payload, headers=headers)
    assert duplicate.status_code == 409


@pytest.mark.parametrize("payload", [
    {"schema_version": 2},
    {"schema_version": 1, "collection_id": "not-a-uuid", "collected_at": "bad", "session_id": 1},
    {"schema_version": 1, "collection_id": str(uuid4()), "collected_at": datetime.utcnow().isoformat(), "session_id": 1},
])
def test_invalid_payloads_are_rejected_without_secret_disclosure(security_app, payload):
    row, token = _credential(security_app)
    response = security_app.client.post("/windows/helper/devices/101/evidence", json=payload, headers={"Authorization": f"Bearer {token}"})
    assert response.status_code in {401, 422}
    assert token not in response.text
    assert row.token_hash not in response.text


def test_auth_errors_do_not_expose_tokens_or_hashes(security_app):
    row, token = _credential(security_app)
    response = security_app.client.post("/windows/helper/devices/101/evidence", json=_evidence(), headers={"Authorization": f"Bearer {token[:-1]}x"})
    assert response.status_code == 401
    assert token not in response.text
    assert row.token_hash not in response.text


def test_audit_events_are_present_for_issue_revoke_and_rotate(security_app):
    issued = _issue(security_app)
    security_app.client.post(f"/windows/helper/credentials/{issued['id']}/rotate")
    security_app.client.post(f"/windows/helper/credentials/{issued['id']}/revoke")
    assert [entry[1]["action"] for entry in security_app.audits] == ["ISSUE", "ROTATE", "REVOKE"]
