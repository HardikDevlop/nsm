from datetime import datetime, timezone
from types import SimpleNamespace

from backend.api.overview_routes import _get_service_states, _registered_job_observability


def _job(job_id, device_id, module, config_id):
    return SimpleNamespace(
        id=job_id,
        next_run_time=datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc),
        args=[device_id, module, 60, config_id],
        kwargs={"secret": "must-not-be-exposed"},
    )


def test_job_ids_and_details_are_live_deterministic_and_safe():
    jobs = [_job("284:interfaces", 284, "interfaces", 7), _job("283:system", 283, "system", 1)]
    ids, details = _registered_job_observability(jobs)
    assert ids == ["283:system", "284:interfaces"]
    assert [item["job_id"] for item in details] == ids
    assert details[0]["config_id"] == 1
    assert details[0]["device_id"] == 283
    assert details[0]["module_name"] == "system"
    assert "secret" not in details[0]


def test_service_status_uses_live_job_list_without_mutation():
    jobs = [_job("283:system", 283, "system", 1)]
    scheduler = SimpleNamespace(running=True, get_jobs=lambda: jobs)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        scheduler_lease_owned=True,
        snmp_polling=SimpleNamespace(scheduler=scheduler),
    )))
    state = _get_service_states(request)
    assert state["snmp_polling"]["registered_jobs"] == len(jobs)
    assert state["snmp_polling"]["job_count"] == len(jobs)
    assert state["snmp_polling"]["registered_job_ids"] == ["283:system"]
    assert state["snmp_polling"]["lease_owned"] is True
    assert state["snmp_polling"]["registered_job_details"][0]["config_id"] == 1
