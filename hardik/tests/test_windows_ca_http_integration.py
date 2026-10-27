"""Isolated HTTP-layer tests for Windows CA routes.

This module mounts only the Windows router.  It never imports ``backend.main``
or runs an application lifespan, migration, seeder, database, storage, or
WinRM operation.  Persistence and certificate parsing are explicit doubles;
FastAPI dependency resolution, authorization, request validation, and response
serialization remain real.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.database.session import get_db
from backend.dependencies import get_current_user
from backend.windows_monitoring import api
from backend.windows_monitoring.ca_bundle_parser import CABundleParseError


def _role(*permissions: str):
    return SimpleNamespace(
        role_name="Synthetic Admin",
        authority_level=80,
        is_system_role=False,
        permissions=[SimpleNamespace(code=value) for value in permissions],
    )


def _user(*permissions: str, sites=(10,)):
    return SimpleNamespace(
        id=7,
        email="windows-ca-test@example.invalid",
        status="active",
        role=_role(*permissions),
        sites=[SimpleNamespace(id=value) for value in sites],
    )


def _bundle(*, bundle_id=12, site_id=10, status="active"):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=bundle_id,
        site_id=site_id,
        name="Synthetic Corporate CA",
        description="Synthetic test metadata",
        sha256_fingerprint="synthetic-fingerprint",
        content_sha256="synthetic-content-hash",
        subject="CN=Synthetic CA",
        issuer="CN=Synthetic CA",
        serial_number="1234",
        not_before=now,
        not_after=now.replace(year=now.year + 1),
        is_ca=True,
        is_self_signed=True,
        trust_type="self_signed_explicit",
        status=status,
        certificate_count=None,
        created_by=7,
        created_at=now,
        updated_at=now,
        revoked_at=None,
        revoked_by=None,
    )


def _keyword_only_audit(calls):
    def record(db, *, actor, action, resource_type=None, resource_id=None, site_id=None, outcome="success", metadata=None, **_):
        calls.append({
            "actor": actor, "action": action, "resource_type": resource_type,
            "resource_id": resource_id, "site_id": site_id, "outcome": outcome,
            "metadata": metadata,
        })
    return record


def _client(request, monkeypatch, *, user, db=None):
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db or Mock()
    client = TestClient(app, raise_server_exceptions=True)
    client.__enter__()
    request.addfinalizer(lambda: client.__exit__(None, None, None))
    return client


def test_upload_is_real_multipart_http_and_returns_metadata_only(request, monkeypatch):
    user = _user("windows_ca:manage")
    client = _client(request, monkeypatch, user=user)
    parsed = SimpleNamespace(
        certificates=(SimpleNamespace(sha256_fingerprint="synthetic-certificate-fingerprint"),),
        certificate_count=1, content_sha256="content-hash",
        subject="CN=Synthetic CA", issuer="CN=Synthetic CA", serial_number="1",
        not_before=None, not_after=None, is_ca=True, is_self_signed=True,
        trust_type="self_signed_explicit",
    )
    bundle = _bundle()
    service = Mock()
    service.duplicate_for_site.return_value = None
    service.create_metadata.return_value = bundle
    monkeypatch.setattr(api, "parse_ca_bundle", lambda value: parsed)
    monkeypatch.setattr(api, "store_pem_bytes", Mock(return_value="ca-secret-key"))
    service.duplicate_for_site.return_value = None
    service.create_metadata.return_value = bundle
    monkeypatch.setattr(api, "WindowsCABundleService", Mock(return_value=service))
    audit_calls = []
    monkeypatch.setattr(api, "record_audit_event", _keyword_only_audit(audit_calls))

    response = client.post(
        "/windows/ca-bundles",
        data={"site_id": "10", "name": "Synthetic Corporate CA", "description": "test"},
        files={"certificate": ("synthetic.pem", b"synthetic certificate bytes", "application/x-pem-file")},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["id"] == 12
    assert "storage_key" not in payload
    assert "protected_path" not in payload
    assert "pem" not in str(payload).lower()
    api.store_pem_bytes.assert_called_once_with(b"synthetic certificate bytes")
    assert audit_calls[0]["action"] == "windows_ca_bundle.create"
    assert audit_calls[0]["resource_id"] == 12


def test_upload_rejects_missing_file_and_invalid_metadata(request, monkeypatch):
    client = _client(request, monkeypatch, user=_user("windows_ca:manage"))
    assert client.post("/windows/ca-bundles", data={"site_id": "10", "name": "CA"}).status_code == 422
    response = client.post(
        "/windows/ca-bundles",
        data={"site_id": "10", "name": "   "},
        files={"certificate": ("synthetic.pem", b"bytes", "application/x-pem-file")},
    )
    assert response.status_code == 422


def test_upload_rejects_invalid_certificate_without_storage(request, monkeypatch):
    client = _client(request, monkeypatch, user=_user("windows_ca:manage"))
    monkeypatch.setattr(api, "parse_ca_bundle", Mock(side_effect=CABundleParseError("invalid_pem", "invalid synthetic certificate")))
    storage = Mock()
    monkeypatch.setattr(api, "store_pem_bytes", storage)

    response = client.post(
        "/windows/ca-bundles",
        data={"site_id": "10", "name": "Synthetic CA"},
        files={"certificate": ("synthetic.pem", b"not-a-real-certificate", "application/x-pem-file")},
    )

    assert response.status_code == 422
    storage.assert_not_called()


def test_list_and_detail_are_site_scoped_and_serialized(request, monkeypatch):
    service = Mock()
    service.list_for_site.return_value = [_bundle()]
    service.get.return_value = _bundle()
    monkeypatch.setattr(api, "WindowsCABundleService", Mock(return_value=service))
    client = _client(request, monkeypatch, user=_user("windows_ca:read", sites=(10,)))

    listed = client.get("/windows/ca-bundles", params={"site_id": 10})
    detail = client.get("/windows/ca-bundles/12")

    assert listed.status_code == 200
    assert listed.json()[0]["site_id"] == 10
    assert detail.status_code == 200
    assert detail.json()["id"] == 12
    assert "storage_key" not in detail.json()
    service.list_for_site.assert_called_once_with(10)


def test_cross_site_list_and_detail_are_hidden(request, monkeypatch):
    service = Mock()
    service.get.return_value = _bundle(site_id=11)
    monkeypatch.setattr(api, "WindowsCABundleService", Mock(return_value=service))
    client = _client(request, monkeypatch, user=_user("windows_ca:read", sites=(10,)))

    assert client.get("/windows/ca-bundles", params={"site_id": 11}).status_code == 404
    assert client.get("/windows/ca-bundles/12").status_code == 404


def test_revoke_requires_manage_and_audits_success(request, monkeypatch):
    service = Mock()
    service.get.return_value = _bundle()
    revoked = _bundle(status="revoked")
    service.revoke.return_value = revoked
    audit_calls = []
    monkeypatch.setattr(api, "WindowsCABundleService", Mock(return_value=service))
    monkeypatch.setattr(api, "record_audit_event", _keyword_only_audit(audit_calls))
    client = _client(request, monkeypatch, user=_user("windows_ca:manage"))

    response = client.post("/windows/ca-bundles/12/revoke")

    assert response.status_code == 200
    assert response.json()["status"] == "revoked"
    assert audit_calls[0]["action"] == "windows_ca_bundle.revoke"
    assert audit_calls[0]["resource_id"] == 12


def test_assignment_replacement_and_unassignment_use_http_contract(request, monkeypatch):
    device = SimpleNamespace(id=7, site_id=10)
    current = SimpleNamespace(device_id=7, ca_bundle_id=11, unassigned_at=None)
    replacement = SimpleNamespace(device_id=7, ca_bundle_id=12, unassigned_at=None)
    service = Mock()
    service.assign.return_value = replacement
    service.get.return_value = _bundle()
    monkeypatch.setattr(api, "_device", Mock(return_value=device))
    monkeypatch.setattr(api, "get_active_device_ca_assignment", Mock(side_effect=[current, replacement]))
    monkeypatch.setattr(api, "WindowsCABundleService", Mock(return_value=service))
    audit_calls = []
    monkeypatch.setattr(api, "record_audit_event", _keyword_only_audit(audit_calls))
    client = _client(request, monkeypatch, user=_user("windows_ca:assign"))

    assigned = client.put("/windows/devices/7/ca-bundle", params={"bundle_id": 12})
    assert assigned.status_code == 200
    assert current.unassigned_at is not None
    assert assigned.json()["bundle_id"] == 12
    assert audit_calls[0]["action"] == "windows_ca_bundle.assign"

    service.unassign.return_value = current
    removed = client.delete("/windows/devices/7/ca-bundle")
    assert removed.status_code == 200
    assert removed.json()["trust_source"] == "global"
    assert audit_calls[1]["action"] == "windows_ca_bundle.unassign"


def test_effective_trust_unavailable_is_safe_http_error(request, monkeypatch):
    device = SimpleNamespace(id=7, site_id=10)
    monkeypatch.setattr(api, "_device", Mock(return_value=device))
    monkeypatch.setattr(api, "get_active_device_ca_assignment", Mock(return_value=None))
    monkeypatch.setattr(api, "resolve_effective_windows_ca", Mock(side_effect=api.EffectiveTrustError("unavailable")))
    client = _client(request, monkeypatch, user=_user("windows_ca:read"))

    response = client.get("/windows/devices/7/ca-bundle")

    assert response.status_code == 200
    assert response.json()["trust_source"] == "unavailable"
    assert "path" not in response.text.lower()


def test_authentication_and_permission_failures_are_http_layer_failures(request, monkeypatch):
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_db] = lambda: Mock()
    unauthenticated = TestClient(app, raise_server_exceptions=True)
    unauthenticated.__enter__()
    request.addfinalizer(lambda: unauthenticated.__exit__(None, None, None))
    assert unauthenticated.get("/windows/ca-bundles", params={"site_id": 10}).status_code == 401

    denied = _client(request, monkeypatch, user=_user("windows_ca:read"))
    response = denied.post(
        "/windows/ca-bundles",
        data={"site_id": "10", "name": "Synthetic CA"},
        files={"certificate": ("synthetic.pem", b"bytes", "application/x-pem-file")},
    )
    assert response.status_code == 403
