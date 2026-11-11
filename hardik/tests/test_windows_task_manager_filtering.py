from types import SimpleNamespace

from backend.windows_monitoring import api


def process(name, pid, memory, cpu, status="ok", creation_time=None, reason=None):
    return SimpleNamespace(
        name=name, process_id=pid, parent_process_id=None,
        working_set_bytes=memory, private_memory_bytes=None,
        thread_count=1, creation_time=creation_time,
    ), SimpleNamespace(process_id=pid, cpu_percent=cpu, status=status, reason=reason)


def process_snapshot(rows):
    processes, cpu = zip(*rows) if rows else ((), ())
    return SimpleNamespace(device_id=1, processes=processes, cpu=cpu,
                           status="ok", reason=None, collected_at="now", age_seconds=0)


def test_process_filter_sort_and_total_before_pagination():
    snapshot = process_snapshot([
        process("Alpha", 3, 300, 10),
        process("beta", 2, 200, None, "unavailable"),
        process("alphabet", 1, 100, 50),
    ])
    result = api._process_response(snapshot, limit=1, offset=0, name="ALP", sort="cpu", direction="desc")
    assert result["total"] == 2
    assert result["items"][0]["pid"] == 1


def test_process_response_exposes_verified_path_classification_and_unknown_metadata():
    system = process("svchost.exe", 4, 100, 0)
    system[0].executable_path = r"C:\Windows\System32\svchost.exe"
    unknown = process("mystery.exe", 5, 100, 0)
    unknown[0].executable_path = None
    result = api._process_response(process_snapshot([system, unknown]), limit=10, offset=0)
    by_pid = {row["pid"]: row for row in result["items"]}
    assert by_pid[4]["classification"] == "windows"
    assert by_pid[4]["classification_source"] == "cim_metadata"
    assert by_pid[5]["classification"] is None


def test_process_null_cpu_sorts_last_in_both_directions():
    snapshot = process_snapshot([process("a", 1, 1, None, "warming_up"), process("b", 2, 1, 1)])
    for direction in ("asc", "desc"):
        result = api._process_response(snapshot, limit=10, offset=0, sort="cpu", direction=direction)
        assert result["items"][-1]["pid"] == 1


def test_default_order_is_unchanged_and_cache_rows_are_not_mutated():
    snapshot = process_snapshot([process("z", 2, 1, 1), process("a", 1, 2, 2)])
    original = [row.process_id for row in snapshot.processes]
    result = api._process_response(snapshot, limit=10, offset=0, sort="name")
    assert [item["pid"] for item in result["items"]] == [1, 2]
    assert [row.process_id for row in snapshot.processes] == original
    unfiltered = api._process_response(snapshot, limit=10, offset=0)
    assert [item["pid"] for item in unfiltered["items"]] == [2, 1]


def test_normal_process_cpu_mapping_uses_active_cpu_result():
    snapshot = process_snapshot([process("worker", 7, 1, 42, creation_time="new")])
    result = api._process_response(snapshot, limit=10, offset=0)
    assert result["items"][0]["cpu_percent"] == 42
    assert result["items"][0]["cpu_status"] == "ok"


def test_pid_reuse_does_not_allow_terminated_result_to_overwrite_active_cpu():
    current, active_cpu = process("worker", 7, 1, 42, creation_time="new")
    terminated_cpu = SimpleNamespace(
        process_id=7, cpu_percent=None, status="terminated", reason="absent_from_current_sample"
    )
    snapshot = SimpleNamespace(
        device_id=1, processes=(current,), cpu=(active_cpu, terminated_cpu),
        status="ok", reason=None, collected_at="now", age_seconds=0,
    )
    result = api._process_response(snapshot, limit=10, offset=0)
    assert result["items"] == [{
        "name": "worker", "pid": 7, "parent_pid": None,
        "working_set_bytes": 1, "private_memory_bytes": None,
            "thread_count": 1, "creation_time": "new", "session_id": None,
            "classification": None, "classification_source": None,
            "classification_confidence": None, "classification_reason": None, "application_group_id": None,
            "cpu_percent": 42,
        "cpu_status": "ok", "cpu_reason": None,
    }]


def test_terminated_process_is_returned_when_no_active_process_has_pid():
    snapshot = process_snapshot([
        process("old", 7, 1, None, status="terminated", reason="absent_from_current_sample")
    ])
    snapshot = SimpleNamespace(
        device_id=1, processes=(), cpu=snapshot.cpu,
        status="ok", reason=None, collected_at="now", age_seconds=0,
    )
    result = api._process_response(snapshot, limit=10, offset=0)
    assert result["items"][0]["cpu_status"] == "terminated"
    assert result["items"][0]["cpu_reason"] == "absent_from_current_sample"


def test_first_sample_warming_up_state_is_preserved():
    snapshot = process_snapshot([
        process("worker", 7, 1, None, status="warming_up", reason="first_sample")
    ])
    result = api._process_response(snapshot, limit=10, offset=0)
    assert result["items"][0]["cpu_percent"] is None
    assert result["items"][0]["cpu_status"] == "warming_up"
    assert result["items"][0]["cpu_reason"] == "first_sample"


def test_missing_cpu_counter_unavailable_state_is_preserved():
    snapshot = process_snapshot([
        process("worker", 7, 1, None, status="unavailable", reason="missing_cpu_time")
    ])
    result = api._process_response(snapshot, limit=10, offset=0)
    assert result["items"][0]["cpu_percent"] is None
    assert result["items"][0]["cpu_status"] == "unavailable"
    assert result["items"][0]["cpu_reason"] == "missing_cpu_time"
