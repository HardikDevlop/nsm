import time
from types import SimpleNamespace

from fastapi import BackgroundTasks

from backend.api import remote_access_routes as routes
from backend.schemas.remote_access import RemoteAccessSessionCreate


class DeliverySession:
    def __init__(self):
        self.committed = False
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True

    def commit(self):
        self.committed = True


def test_remote_access_notification_delivery_runs_with_independent_session(monkeypatch):
    delivery_db = DeliverySession()
    calls = []

    monkeypatch.setattr(routes, "SessionLocal", lambda: delivery_db)
    def deliver(db, notification_ids):
        calls.append((db, notification_ids))
        time.sleep(0.02)
    monkeypatch.setattr(routes, "deliver_notification_ids", deliver)

    routes._deliver_remote_access_notifications([11], "session-uuid")

    assert calls == [(delivery_db, [11])]
    assert delivery_db.committed is True
    assert delivery_db.closed is True


def test_remote_access_notification_failure_does_not_escape_or_change_session(monkeypatch, caplog):
    delivery_db = DeliverySession()
    monkeypatch.setattr(routes, "SessionLocal", lambda: delivery_db)
    monkeypatch.setattr(routes, "deliver_notification_ids", lambda *_: (_ for _ in ()).throw(RuntimeError("smtp down")))

    session = SimpleNamespace(status="connected")
    routes._deliver_remote_access_notifications([11], "session-uuid")

    assert session.status == "connected"
    assert delivery_db.closed is True
    assert "notification-failed session_uuid=session-uuid" in caplog.text


def test_create_route_only_schedules_delivery_after_persistence(monkeypatch):
    now = __import__("datetime").datetime.now()
    record = SimpleNamespace(
        id=1, session_uuid="session-uuid", device_id=1, credential_id=None,
        user_id=7, protocol="ssh", port=22, device_username="operator",
        status="connected", started_at=now, last_activity_at=now,
        ended_at=None, disconnect_reason=None, source_ip=None, user_name=None,
        created_at=now,
    )
    device = SimpleNamespace(site_id=1)
    manager_db = SimpleNamespace(commit=lambda: None, rollback=lambda: None, is_active=True,
                                 get=lambda *_: device)
    manager = SimpleNamespace(db=manager_db, create_session=lambda **_: record)
    scheduled = BackgroundTasks()
    persisted_ids = []

    monkeypatch.setattr(routes, "get_user_permission_codes", lambda _: {"remote_access:connect"})
    monkeypatch.setattr(routes, "can_access_site", lambda *_: True)
    monkeypatch.setattr(routes, "_record_remote_access_connected_alert",
                        lambda _db, _session, ids: (ids.extend([11]), persisted_ids.extend(ids), True)[-1])
    monkeypatch.setattr(routes, "deliver_notification_ids",
                        lambda *_: (_ for _ in ()).throw(AssertionError("SMTP ran in request path")))
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))
    payload = RemoteAccessSessionCreate(device_id=1, protocol="ssh", username="operator", secret="secret")

    result = routes.create_remote_session(payload, request, scheduled, manager_db, SimpleNamespace(id=7), manager)

    assert result.session_uuid == "session-uuid"
    assert persisted_ids == [11]
    assert len(scheduled.tasks) == 1
