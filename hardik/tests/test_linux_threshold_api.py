import asyncio
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException

from backend.api.routes import _authorized_alert
from backend.linux_monitoring.api import _authorized_linux_server, update_linux_server_thresholds
from backend.linux_monitoring.schemas import LinuxServerThresholdConfigUpdate


def test_threshold_schema_rejects_warning_at_or_above_critical():
    with pytest.raises(ValueError):
        LinuxServerThresholdConfigUpdate(cpu_warning_percent=95, cpu_critical_percent=95)


def test_threshold_server_access_is_forbidden_outside_site():
    db = Mock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(id=11, site_id=8)
    user = SimpleNamespace()
    with patch("backend.linux_monitoring.api.can_access_site", return_value=False):
        with pytest.raises(HTTPException) as exc:
            _authorized_linux_server(11, db, user)
    assert exc.value.status_code == 403


def test_threshold_update_uses_authorized_server_and_commits():
    db = Mock()
    server = SimpleNamespace(id=11, site_id=8)
    config = SimpleNamespace(linux_server_id=11)
    db.query.return_value.filter_by.return_value.first.return_value = config
    payload = LinuxServerThresholdConfigUpdate(cpu_warning_percent=70, cpu_critical_percent=90)
    user = SimpleNamespace()
    with patch("backend.linux_monitoring.api.can_access_site", return_value=True), patch(
        "backend.linux_monitoring.api.service.get_server", return_value=server
    ):
        result = update_linux_server_thresholds(11, payload, db, user)
    assert result is config
    assert config.cpu_warning_percent == 70
    assert config.cpu_critical_percent == 90
    db.commit.assert_called_once()


def test_linux_alert_isolated_from_other_site():
    db = Mock()
    db.get.return_value = SimpleNamespace(id=11, site_id=8)
    alert = SimpleNamespace(id=99, linux_server_id=11, device_id=None)
    with patch("backend.api.routes.can_access_site", return_value=False):
        with pytest.raises(HTTPException) as exc:
            _authorized_alert(alert, db, SimpleNamespace())
    assert exc.value.status_code == 404


def test_monitoring_start_checks_site_before_credentials_or_scheduler(monkeypatch):
    from backend.linux_monitoring import api

    db = Mock()
    request = SimpleNamespace()
    user = SimpleNamespace()
    payload = SimpleNamespace(username=None)
    with patch.object(api, "_authorized_linux_server", side_effect=HTTPException(status_code=403)), patch.object(
        api.service, "save_monitoring_credential"
    ) as save_credential, patch.object(api, "_scheduler") as scheduler:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(api.start_linux_monitoring(38, payload, request, db, user))
    assert exc.value.status_code == 403
    save_credential.assert_not_called()
    scheduler.assert_not_called()


def test_monitoring_stop_checks_site_before_scheduler():
    from backend.linux_monitoring import api

    db = Mock()
    request = SimpleNamespace()
    user = SimpleNamespace()
    with patch.object(api, "_authorized_linux_server", side_effect=HTTPException(status_code=403)), patch.object(
        api, "_scheduler"
    ) as scheduler:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(api.stop_linux_monitoring(38, request, db, user))
    assert exc.value.status_code == 403
    scheduler.assert_not_called()
