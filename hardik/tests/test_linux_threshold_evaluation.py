from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.linux_monitoring.threshold_evaluation import _evaluate_one, classify_metric


def test_classifies_normal_warning_and_critical_values():
    assert classify_metric(79.9, 80, 95) == "NORMAL"
    assert classify_metric(80, 80, 95) == "WARNING"
    assert classify_metric(95, 80, 95) == "CRITICAL"


def test_missing_metric_is_unavailable_without_recovery():
    assert classify_metric(None, 80, 95) == "UNAVAILABLE"
    db = Mock()
    server = SimpleNamespace(id=7, hostname="ubuntu")
    with patch("backend.linux_monitoring.threshold_evaluation._active_alert") as active, patch(
        "backend.linux_monitoring.threshold_evaluation.resolve_alert"
    ) as resolve:
        result = _evaluate_one(db, server, "cpu", None, 80, 95)
    assert result.state == "UNAVAILABLE"
    active.assert_not_called()
    resolve.assert_not_called()


def test_warning_creates_one_alert_and_repeated_warning_is_duplicate_free():
    db = Mock()
    server = SimpleNamespace(id=7, hostname="ubuntu")
    active = SimpleNamespace(severity="warning")
    with patch("backend.linux_monitoring.threshold_evaluation._active_alert", side_effect=[None, active]), patch(
        "backend.linux_monitoring.threshold_evaluation.create_threshold_alert"
    ) as create:
        _evaluate_one(db, server, "cpu", 82, 80, 95)
        _evaluate_one(db, server, "cpu", 84, 80, 95)
    create.assert_called_once()


def test_critical_transition_resolves_previous_and_creates_critical_alert():
    db = Mock()
    server = SimpleNamespace(id=7, hostname="ubuntu")
    active = SimpleNamespace(severity="warning")
    with patch("backend.linux_monitoring.threshold_evaluation._active_alert", return_value=active), patch(
        "backend.linux_monitoring.threshold_evaluation.resolve_alert"
    ) as resolve, patch(
        "backend.linux_monitoring.threshold_evaluation.create_threshold_alert"
    ) as create:
        result = _evaluate_one(db, server, "memory", 97, 80, 95)
    assert result.state == "CRITICAL"
    resolve.assert_called_once()
    create.assert_called_once()
    assert create.call_args.kwargs["severity"] == "critical"
    assert create.call_args.kwargs["linux_server_id"] == server.id


def test_recovery_resolves_active_alert():
    db = Mock()
    server = SimpleNamespace(id=7, hostname="ubuntu")
    active = SimpleNamespace(severity="critical")
    with patch("backend.linux_monitoring.threshold_evaluation._active_alert", return_value=active), patch(
        "backend.linux_monitoring.threshold_evaluation.resolve_alert"
    ) as resolve, patch(
        "backend.linux_monitoring.threshold_evaluation.create_threshold_alert"
    ) as create:
        result = _evaluate_one(db, server, "disk", 40, 80, 95)
    assert result.state == "NORMAL"
    resolve.assert_called_once()
    create.assert_not_called()
