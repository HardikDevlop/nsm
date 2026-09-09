from datetime import datetime, timedelta

import pytest

from backend.api.change_routes import ApprovalPayload, ChangeCreatePayload, ChangeUpdatePayload, _validate_links, _validate_owner, approve_change, link_problem, reject_change, router, unlink_problem
from backend.changes.service import ChangeTransitionError, ALLOWED_TRANSITIONS, transition_change
from backend.models import ChangeHistory, ChangeProblem, ChangeRequest, Problem, User
from sqlalchemy.exc import IntegrityError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.database.session import Base


def test_change_request_validates_maintenance_window_and_plans():
    start = datetime(2026, 8, 29, 10, 0)
    payload = ChangeCreatePayload(title="Upgrade core", risk="high", impact="high", maintenance_start=start, maintenance_end=start + timedelta(hours=1), implementation_plan="Apply change", rollback_plan="Restore backup")
    assert payload.rollback_plan == "Restore backup"
    with pytest.raises(ValueError):
        ChangeCreatePayload(title="Invalid", maintenance_start=start, maintenance_end=start)


def test_change_update_restricts_lifecycle_values():
    assert ChangeUpdatePayload(status="rolled_back").status == "rolled_back"
    with pytest.raises(ValueError):
        ChangeUpdatePayload(status="random")


def test_change_routes_cover_request_approval_links_and_audit_workflow():
    paths = {route.path for route in router.routes}
    assert "/api/v1/changes" in paths
    assert "/api/v1/changes/{change_id}/approve" in paths
    assert "/api/v1/changes/{change_id}/cis/{ci_id}" in paths
    assert "/api/v1/changes/{change_id}/incidents/{incident_id}" in paths
    assert "/api/v1/changes/available/problems" in paths
    assert "/api/v1/changes/{change_id}/problems/{problem_id}" in paths


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_change_core_fields_persist_and_owner_must_be_active():
    db = _db()
    db.add_all([
        User(id=1, name="Active", email="active@example.com", password_hash="x", status="active"),
        User(id=2, name="Inactive", email="inactive@example.com", password_hash="x", status="inactive"),
    ])
    change = ChangeRequest(number="CHG-000001", title="Core upgrade", category="normal", risk="high", impact="medium", priority="p1", owner_id=1, approval_required=True, status="draft", created_at=datetime.utcnow(), updated_at=datetime.utcnow(), implementation_result="completed", rollback_result="restored", rollback_status="completed")
    db.add(change); db.commit(); db.refresh(change)
    assert (change.priority, change.owner_id, change.approval_required) == ("p1", 1, True)
    assert change.implementation_result == "completed" and change.rollback_status == "completed"
    _validate_owner(db, 1)
    with pytest.raises(Exception):
        _validate_owner(db, 2)


def test_change_lifecycle_uses_explicit_transitions_and_dedicated_history():
    db = _db(); now = datetime.utcnow()
    change = ChangeRequest(number="CHG-000002", title="Lifecycle", category="normal", risk="low", impact="low", priority="p3", status="draft", created_at=now, updated_at=now)
    db.add(change); db.flush()
    for target in ("submitted", "approved", "scheduled", "implementing", "implemented", "closed"):
        transition_change(db, change, target, 1)
    assert change.status == "closed"
    assert [row.action for row in db.query(ChangeHistory).order_by(ChangeHistory.id).all()] == ["submitted", "approved", "scheduled", "implementation_started", "implementation_completed", "closed"]
    with pytest.raises(ChangeTransitionError, match="Invalid change transition"):
        transition_change(db, change, "draft", 1)
    assert ALLOWED_TRANSITIONS["submitted"] == {"approved", "rejected"}


def test_change_routes_expose_core_action_endpoints():
    paths = {route.path for route in router.routes}
    assert {
        "/api/v1/changes/{change_id}/submit",
        "/api/v1/changes/{change_id}/approve",
        "/api/v1/changes/{change_id}/reject",
        "/api/v1/changes/{change_id}/schedule",
        "/api/v1/changes/{change_id}/implementation/start",
        "/api/v1/changes/{change_id}/implementation/complete",
        "/api/v1/changes/{change_id}/implementation/fail",
        "/api/v1/changes/{change_id}/rollback",
        "/api/v1/changes/{change_id}/close",
    }.issubset(paths)


def test_approval_required_approval_metadata_and_rejection_are_persisted():
    db = _db(); now = datetime.utcnow()
    approver = User(id=7, name="Approver", email="approver@example.com", password_hash="x", status="active")
    db.add(approver)
    approved = ChangeRequest(number="CHG-000007", title="Approved", category="normal", risk="low", impact="low", priority="p2", approval_required=True, status="submitted", created_at=now, updated_at=now)
    rejected = ChangeRequest(number="CHG-000008", title="Rejected", category="normal", risk="low", impact="low", priority="p4", approval_required=True, status="submitted", created_at=now, updated_at=now)
    db.add_all([approved, rejected]); db.flush()
    approve_change(approved.id, ApprovalPayload(comment="Approved window"), db, approver)
    reject_change(rejected.id, ApprovalPayload(comment="Insufficient rollback plan"), db, approver)
    assert approved.status == "approved" and approved.approved_by == 7 and approved.approved_at is not None and approved.approval_comment == "Approved window"
    assert rejected.status == "rejected" and rejected.rejected_by == 7 and rejected.rejected_at is not None and rejected.rejection_comment == "Insufficient rollback plan"
    assert {row.action for row in db.query(ChangeHistory).all()} >= {"approved", "rejected"}


def test_problem_relationship_persists_rejects_duplicates_and_unlinks_safely():
    db = _db(); now = datetime.utcnow()
    user = User(id=21, name="Operator", email="operator@example.com", password_hash="x", status="active")
    change = ChangeRequest(number="CHG-000021", title="Link problem", category="normal", risk="low", impact="low", priority="p3", status="draft", created_at=now, updated_at=now)
    problem = Problem(id=31, number="PRB-000031", title="Persisted problem", category="network", priority="p3", status="open", created_at=now, updated_at=now)
    db.add_all([user, change, problem]); db.flush()
    link_problem(change.id, problem.id, db, user)
    assert db.query(ChangeProblem).filter_by(change_id=change.id, problem_id=problem.id).count() == 1
    with pytest.raises(Exception, match="already linked"):
        link_problem(change.id, problem.id, db, user)
    unlink_problem(change.id, problem.id, db, user)
    assert db.query(ChangeProblem).filter_by(change_id=change.id, problem_id=problem.id).count() == 0
    assert db.get(Problem, problem.id) is not None
    assert {row.action for row in db.query(ChangeHistory).all()} >= {"problem_linked", "problem_unlinked"}


def test_invalid_problem_link_is_rejected_without_creating_a_record():
    db = _db()
    with pytest.raises(Exception, match="problems not found"):
        _validate_links(db, [], [], [404])
