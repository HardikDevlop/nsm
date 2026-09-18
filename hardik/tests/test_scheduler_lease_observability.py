from types import SimpleNamespace

from backend.api.overview_routes import _get_service_states


class FakeAPScheduler:
    running = False

    def get_jobs(self):
        return []


def _request(owned, running=False):
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                scheduler_lease_owned=owned,
                snmp_polling=SimpleNamespace(scheduler=FakeAPScheduler()) if running is not None else None,
            )
        )
    )


def test_service_status_reads_authoritative_app_lease_state():
    state = _get_service_states(_request(True, False))
    assert state["snmp_polling"]["lease_owned"] is True

    state = _get_service_states(_request(False, True))
    assert state["snmp_polling"]["lease_owned"] is False


def test_scheduler_running_does_not_imply_lease_ownership():
    request = _request(False, True)
    request.app.state.snmp_polling.scheduler.running = True
    assert _get_service_states(request)["snmp_polling"]["lease_owned"] is False
