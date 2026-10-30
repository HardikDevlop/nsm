from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.windows_monitoring.threshold_evaluation import (
    DEFAULT_THRESHOLD,
    _usage_for_metric,
    evaluate_metric,
    apply_transition_alert,
    ThresholdTransition,
)


@pytest.mark.parametrize("metric,data,expected", [
    ("cpu", {"usage_percent": 40}, 40),
    ("memory", {"usage_percent": 74.8}, 74.8),
    ("disk", [{"usage_percent": 20}, {"usage_percent": 40}], 40),
])
def test_usage_extraction_includes_threshold_boundary(metric, data, expected):
    assert _usage_for_metric(metric, data) == expected


def test_disk_uses_one_device_level_maximum_volume_value():
    assert _usage_for_metric("disk", [{"usage_percent": 39}, {"usage_percent": 81}]) == 81


@pytest.mark.parametrize("data", [None, {}, {"usage_percent": None}, {"usage_percent": "bad"}, {"usage_percent": float("nan")}])
def test_invalid_cpu_values_are_ignored(data):
    assert _usage_for_metric("cpu", data) is None


def test_invalid_disk_volumes_are_ignored():
    assert _usage_for_metric("disk", [{"usage_percent": None}, {}, {"usage_percent": "bad"}]) is None


def test_default_threshold_is_40():
    assert DEFAULT_THRESHOLD == 40


def test_evaluation_has_no_global_alert_or_incident_dependencies():
    from backend.windows_monitoring import threshold_evaluation

    assert not hasattr(threshold_evaluation, "Alert")
    assert not hasattr(threshold_evaluation, "Incident")


class _Query:
    def __init__(self, value):
        self.value = value

    def filter(self, *args):
        return self

    def with_for_update(self):
        return self

    def first(self):
        return self.value


class _SequenceQuery(_Query):
    def __init__(self, *values):
        super().__init__(values[0])
        self.values = list(values)

    def first(self):
        return self.values.pop(0)


def _db(config, state):
    db = Mock()
    db.query.side_effect = [_Query(config), _Query(state)]
    return db


def test_normal_to_warning_transition_is_returned_without_alert_creation():
    state = SimpleNamespace(state="normal", last_value=None, threshold_at_transition=None, last_transition_at=None, last_error=None)
    db = _db(SimpleNamespace(memory_threshold=40), state)

    result = evaluate_metric(db, 7, "memory", {"usage_percent": 40})

    assert result.transition == "warning"
    assert result.previous_state == "normal"
    assert result.state == "warning"
    assert state.last_value == 40
    assert not any(call.args and "Alert" in str(call.args[0]) for call in db.add.call_args_list)


def test_warning_to_normal_transition_is_recovery_and_repeated_warning_is_deduplicated():
    state = SimpleNamespace(state="warning", last_value=75, threshold_at_transition=40, last_transition_at=None, last_error=None)
    db = _db(SimpleNamespace(memory_threshold=40), state)
    recovery = evaluate_metric(db, 7, "memory", {"usage_percent": 39.9})
    assert recovery.transition == "recovery"
    assert recovery.state == "normal"

    state.state = "warning"
    db = _db(SimpleNamespace(memory_threshold=40), state)
    repeated = evaluate_metric(db, 7, "memory", {"usage_percent": 74.8})
    assert repeated.transition is None
    assert repeated.state == "warning"


def test_unavailable_data_preserves_previous_state():
    state = SimpleNamespace(state="warning")
    db = _db(SimpleNamespace(cpu_threshold=40), state)

    result = evaluate_metric(db, 9, "cpu", {"usage_percent": None})

    assert result.evaluated is False
    assert result.state == "warning"


class _Insert:
    def values(self, **kwargs):
        return self

    def on_conflict_do_nothing(self, **kwargs):
        return self

    def returning(self, *args):
        return self


@pytest.mark.parametrize(
    ("usage", "expected_state", "expected_transition"),
    [(40, "warning", "warning"), (39.9, "normal", None)],
)
def test_first_evaluation_uses_normal_as_previous_state(monkeypatch, usage, expected_state, expected_transition):
    config_query = _Query(SimpleNamespace(cpu_threshold=40))
    state_query = _Query(SimpleNamespace(state="warning" if usage >= 40 else "normal"))
    db = Mock()
    db.query.side_effect = [config_query, _SequenceQuery(None, state_query.value)]
    db.execute.return_value.scalar_one_or_none.return_value = 1
    monkeypatch.setattr("backend.windows_monitoring.threshold_evaluation.pg_insert", lambda model: _Insert())

    result = evaluate_metric(db, 7, "cpu", {"usage_percent": usage})

    assert result.previous_state == "normal"
    assert result.state == expected_state
    assert result.transition == expected_transition


def test_first_evaluation_conflict_uses_winning_locked_state(monkeypatch):
    config_query = _Query(SimpleNamespace(cpu_threshold=40))
    winning_state = SimpleNamespace(state="warning", last_value=70, threshold_at_transition=40, last_transition_at=None, last_error=None)
    state_query = _Query(winning_state)
    db = Mock()
    db.query.side_effect = [config_query, _SequenceQuery(None, winning_state)]
    db.execute.return_value.scalar_one_or_none.return_value = None
    monkeypatch.setattr("backend.windows_monitoring.threshold_evaluation.pg_insert", lambda model: _Insert())

    result = evaluate_metric(db, 7, "cpu", {"usage_percent": 75})

    assert result.previous_state == "warning"
    assert result.transition is None


def test_warning_transition_projects_to_one_global_alert_without_direct_email(monkeypatch):
    created = Mock()
    monkeypatch.setattr("backend.services.alerting.create_threshold_alert", created)
    transition = ThresholdTransition(7, "memory", "normal", "warning", 74.8, 40, "warning", True)
    intents = []

    apply_transition_alert(Mock(), transition, device_label="WIN-7", notification_intents=intents)

    created.assert_called_once()
    assert created.call_args.args[1:5] == (7, "Windows Memory Usage Threshold", "Windows device WIN-7: memory usage is 74.80%; configured threshold is 40.00%.", "warning")
    assert created.call_args.kwargs["notification_intents"] is intents


def test_recovery_transition_resolves_matching_alert(monkeypatch):
    active = SimpleNamespace()
    db = Mock()
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = active
    resolved = Mock()
    monkeypatch.setattr("backend.services.alerting.resolve_alert", resolved)
    transition = ThresholdTransition(7, "disk", "warning", "normal", 20, 40, "recovery", True)
    intents = []

    apply_transition_alert(db, transition, device_label="WIN-7", notification_intents=intents)

    resolved.assert_called_once()
    assert resolved.call_args.args[1] is active
    assert resolved.call_args.kwargs["notification_intents"] is intents
