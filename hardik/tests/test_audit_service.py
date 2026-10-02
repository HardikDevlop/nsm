from types import SimpleNamespace

from backend.services.audit import record_audit_event, redact_sensitive


class FakeDB:
    def __init__(self):
        self.items = []

    def add(self, item):
        self.items.append(item)

    def commit(self):
        return None

    def refresh(self, item):
        return None

    def rollback(self):
        return None


def test_structured_event_and_request_context():
    db = FakeDB()
    actor = SimpleNamespace(id=7, email="admin@example.com", role=SimpleNamespace(role_name="Admin"))
    event = record_audit_event(db, actor=actor, action="UPDATE", resource_type="device", resource_id=9, target_user_id=4, site_id=2, request_method="PATCH", request_path="/api/v1/devices/9", source_ip="192.0.2.1", user_agent="test-agent")
    assert event is db.items[0]
    assert event.user_id == 7 and event.actor_username == "admin@example.com"
    assert event.actor_role == "Admin" and event.resource_id == 9
    assert event.target_user_id == 4 and event.site_id == 2
    assert event.request_method == "PATCH" and event.request_path.endswith("/9")


def test_old_new_and_metadata_values_are_redacted_recursively():
    data = {"name": "safe", "password": "hidden", "nested": [{"api_key": "hidden", "value": 3}]}
    assert redact_sensitive(data) == {"name": "safe", "password": "[REDACTED]", "nested": [{"api_key": "[REDACTED]", "value": 3}]}
    db = FakeDB()
    event = record_audit_event(db, action="UPDATE", old_values=data, new_values={"community_string": "x"}, metadata={"authorization_header": "Bearer x", "ok": True})
    assert event.old_values["password"] == "[REDACTED]"
    assert event.new_values["community_string"] == "[REDACTED]"
    assert event.metadata_json["authorization_header"] == "[REDACTED]"


def test_optional_fields_can_be_null_and_failure_is_safe():
    db = FakeDB()
    event = record_audit_event(db, action="READ")
    assert event.user_id is None and event.old_values is None and event.metadata_json is None
    assert event.resource_type is None
