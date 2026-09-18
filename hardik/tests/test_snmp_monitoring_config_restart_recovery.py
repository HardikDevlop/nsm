from types import SimpleNamespace

from backend.services.snmp_polling import _is_restart_restorable_config


def test_running_and_error_enabled_configs_restore():
    assert _is_restart_restorable_config(True, "running")
    assert _is_restart_restorable_config(True, "error")


def test_unsupported_and_disabled_configs_do_not_restore():
    assert not _is_restart_restorable_config(True, "not_supported")
    assert not _is_restart_restorable_config(False, "error")
    assert not _is_restart_restorable_config(False, "running")


def test_waiting_first_poll_is_not_currently_production_runnable_state():
    assert not _is_restart_restorable_config(True, "waiting_first_poll")


def test_error_diagnostic_is_unchanged_until_success():
    config = SimpleNamespace(enabled=True, status="error", error_message="timeout")
    assert _is_restart_restorable_config(config.enabled, config.status)
    assert config.status == "error"
    assert config.error_message == "timeout"
