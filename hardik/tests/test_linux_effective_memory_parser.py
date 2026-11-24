import pytest

from backend.linux_monitoring.metrics import parse_linux_effective_memory_extend_output


VALID = "version=1 MemTotalKiB=16191488 MemAvailableKiB=9227472"


def test_parses_values_converts_units_and_reports_semantics():
    result = parse_linux_effective_memory_extend_output(VALID)

    assert result.version == 1
    assert result.total_bytes == 16191488 * 1024
    assert result.available_bytes == 9227472 * 1024
    assert result.used_bytes == (16191488 - 9227472) * 1024
    assert result.utilization_percent == pytest.approx(
        ((16191488 - 9227472) / 16191488) * 100
    )
    assert result.source == "net-snmp-extend"
    assert result.semantic == "linux_proc_meminfo_memavailable"


@pytest.mark.parametrize(
    "available, expected_percent",
    [("0", 100.0), ("16191488", 0.0)],
)
def test_accepts_zero_or_fully_available_memory(available, expected_percent):
    result = parse_linux_effective_memory_extend_output(
        f"version=1 MemTotalKiB=16191488 MemAvailableKiB={available}"
    )
    assert result.utilization_percent == expected_percent


@pytest.mark.parametrize(
    "output",
    [
        "version=1 MemTotalKiB=16191488",
        "version=2 MemTotalKiB=16191488 MemAvailableKiB=9227472",
        "version=-1 MemTotalKiB=16191488 MemAvailableKiB=9227472",
        "version=1 MemTotalKiB=0 MemAvailableKiB=0",
        "version=1 MemTotalKiB=-1 MemAvailableKiB=0",
        "version=1 MemTotalKiB=16191488 MemAvailableKiB=-1",
        "version=1 MemTotalKiB=16191488 MemAvailableKiB=9227472 MemFreeKiB=1",
        "version=1 MemTotalKiB=16191488 MemTotalKiB=16191488 MemAvailableKiB=9227472",
        "version=1 MemTotalKiB=16MiB MemAvailableKiB=9227472",
        "version=1 MemTotalKiB=16191488 MemAvailableKiB=20000000",
    ],
)
def test_rejects_invalid_or_unsafe_output(output):
    with pytest.raises(ValueError):
        parse_linux_effective_memory_extend_output(output)
