from backend.windows_monitoring.cim import WindowsProcessResult
from backend.windows_monitoring.process_cpu import calculate_process_cpu


def process(pid=7, creation="2026-01-01T00:00:00+00:00", cpu=0.0):
    return WindowsProcessResult("worker.exe", pid, 1, 1, None, creation_time=creation, cpu_time_seconds=cpu)


def calculate(previous, current, previous_time=10.0, current_time=12.0, processors=1):
    return calculate_process_cpu(previous, current, previous_monotonic_seconds=previous_time, current_monotonic_seconds=current_time, logical_processor_count=processors)


def test_normal_cpu_usage():
    result = calculate([process(cpu=10)], [process(cpu=11)])
    assert result[0].cpu_percent == 50
    assert result[0].status == "ok"


def test_multi_core_normalization():
    result = calculate([process(cpu=10)], [process(cpu=12)], processors=4)
    assert result[0].cpu_percent == 25


def test_first_sample_is_warming_up():
    result = calculate([], [process(cpu=10)])
    assert result[0].status == "warming_up"
    assert result[0].reason == "first_sample_or_new_process"


def test_missing_cpu_counter_is_unavailable():
    result = calculate([process(cpu=None)], [process(cpu=10)])
    assert result[0].status == "unavailable"
    assert result[0].reason == "missing_cpu_time"


def test_pid_reuse_does_not_inherit_cpu():
    result = calculate([process(cpu=10, creation="old")], [process(cpu=11, creation="new")])
    current = next(item for item in result if item.process_id == 7 and item.reason == "pid_reused")
    assert current.status == "warming_up"
    assert current.cpu_percent is None


def test_counter_reset_is_unavailable():
    result = calculate([process(cpu=20)], [process(cpu=10)])
    assert result[0].reason == "cpu_counter_reset"


def test_process_termination_is_reported():
    result = calculate([process(cpu=10)], [])
    assert result == [result[0]]
    assert result[0].status == "terminated"
    assert result[0].reason == "absent_from_current_sample"


def test_invalid_elapsed_time_is_unavailable():
    result = calculate([process(cpu=10)], [process(cpu=11)], previous_time=2, current_time=2)
    assert result[0].reason == "invalid_elapsed_time"


def test_missing_creation_time_is_unavailable():
    result = calculate([process(cpu=10)], [process(creation=None, cpu=11)])
    assert result[0].reason == "missing_creation_time"


def test_invalid_logical_processor_count_is_unavailable():
    result = calculate([process(cpu=10)], [process(cpu=11)], processors=0)
    assert result[0].reason == "invalid_logical_processor_count"


def test_cpu_above_expected_range_is_unavailable():
    result = calculate([process(cpu=0)], [process(cpu=10)], previous_time=10, current_time=10.1)
    assert result[0].reason == "impossible_cpu_percentage"


def test_zero_cpu_usage_is_valid():
    result = calculate([process(cpu=10)], [process(cpu=10)])
    assert result[0].cpu_percent == 0
    assert result[0].status == "ok"
