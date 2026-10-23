from datetime import datetime

import pytest
from pydantic import ValidationError

from backend.windows_monitoring.models import WINDOWS_MONITORING_TABLES, WindowsCredential
from backend.windows_monitoring.schemas import (
    WindowsCredentialCreate,
    WindowsCredentialPersisted,
    WindowsCredentialRead,
    WindowsCredentialUpdate,
)


def test_windows_credential_is_one_additive_device_scoped_table():
    assert [table.name for table in WINDOWS_MONITORING_TABLES] == [
        "windows_credentials", "windows_system_snapshots", "windows_metric_snapshots", "windows_hardware_snapshots", "windows_event_logs"
    ]
    assert WindowsCredential.__table__.c.device_id.foreign_keys
    assert any(
        constraint.name == "uq_windows_credentials_device_id"
        for constraint in WindowsCredential.__table__.constraints
    )
    assert WindowsCredential.__table__.c.encrypted_secret.nullable is False


def test_password_contract_requires_secret_and_has_no_non_password_auth():
    credential = WindowsCredentialCreate(
        device_id=7, username="Administrator", secret="plain-input"
    )
    assert credential.auth_method == "password"
    assert credential.secret.get_secret_value() == "plain-input"

    with pytest.raises(ValidationError):
        WindowsCredentialCreate(device_id=7, username="Administrator", secret="")

    with pytest.raises(ValidationError):
        WindowsCredentialCreate(
            device_id=7, auth_method="certificate", username="Administrator", secret="x"
        )


def test_read_contract_excludes_secret_and_encrypted_material():
    fields = set(WindowsCredentialRead.model_fields)
    assert "secret" not in fields
    assert "encrypted_secret" not in fields
    assert WindowsCredentialUpdate.model_fields["secret"].annotation is not None

    internal = WindowsCredentialPersisted(
        device_id=7, username="Administrator", encrypted_secret="fernet-token"
    )
    assert internal.encrypted_secret == "fernet-token"
    with pytest.raises(ValidationError):
        WindowsCredentialPersisted(
            device_id=7,
            username="Administrator",
            encrypted_secret="fernet-token",
            secret="plain-input",
        )
