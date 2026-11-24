from io import StringIO
from unittest.mock import mock_open

import pytest

from backend.linux_monitoring.metrics import parse_linux_effective_memory_extend_output
from tools import agnigate_linux_memavailable as script


VALID_MEMINFO = """\
MemTotal:       16191488 kB
MemFree:         2142408 kB
MemAvailable:    9227472 kB
Buffers:          250860 kB
Cached:          7246968 kB
Active(anon):     143704 kB
Inactive(anon):  6351644 kB
Active(file):    2491896 kB
Inactive(file):  4805760 kB
KReclaimable:     418852 kB
SReclaimable:     418852 kB
HugePages_Total:       0
DirectMap4k:      508924 kB
"""


def test_reads_meminfo_and_emits_parser_compatible_output(monkeypatch, capsys):
    monkeypatch.setattr(script, "read_meminfo", lambda: (16191488, 9227472))

    assert script.main([]) == 0
    captured = capsys.readouterr()
    assert captured.out == "version=1 MemTotalKiB=16191488 MemAvailableKiB=9227472\n"
    assert captured.err == ""
    parsed = parse_linux_effective_memory_extend_output(captured.out)
    assert parsed.total_kib == 16191488
    assert parsed.available_kib == 9227472


def test_parse_meminfo_uses_required_kib_values():
    assert script.parse_meminfo(VALID_MEMINFO) == (16191488, 9227472)


@pytest.mark.parametrize(
    "content",
    [
        "MemTotal: 10 kB\n",
        "MemTotal: ten kB\nMemAvailable: 5 kB\n",
        "MemTotal: 10 kB\nMemAvailable: five kB\n",
        "MemTotal 10 kB\nMemAvailable: 5 kB\n",
        "Active(anon: 10 kB\nMemTotal: 10 kB\nMemAvailable: 5 kB\n",
        "MemTotal: 10 MB\nMemAvailable: 5 kB\n",
        "MemTotal: 10 kB\nMemAvailable: 5 MB\n",
        "MemTotal: 10 kB\nMemAvailable: 5 kB\nMemAvailable: 4 kB\n",
        "MemTotal: 0 kB\nMemAvailable: 0 kB\n",
        "MemTotal: -1 kB\nMemAvailable: 0 kB\n",
        "MemTotal: 10 kB\nMemAvailable: -1 kB\n",
        "MemTotal: 10 kB\nMemAvailable: 11 kB\n",
        "MemTotal: 10 kB\nMemAvailable: 5 kB\nnot meminfo\n",
    ],
)
def test_rejects_malformed_missing_duplicate_or_invalid_meminfo(content):
    with pytest.raises(ValueError):
        script.parse_meminfo(content)


def test_main_failure_has_no_partial_stdout_or_sensitive_error(monkeypatch, capsys):
    monkeypatch.setattr(script, "read_meminfo", lambda: (_ for _ in ()).throw(ValueError("secret")))

    assert script.main([]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "unable to read valid Linux memory information\n"
    assert "secret" not in captured.err


def test_main_rejects_arguments_without_reading_meminfo(monkeypatch, capsys):
    monkeypatch.setattr(
        script,
        "read_meminfo",
        lambda: pytest.fail("argument validation must precede meminfo access"),
    )
    assert script.main(["/tmp/other-meminfo"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "does not accept arguments" in captured.err


def test_read_meminfo_accepts_injected_stream_only_for_tests():
    assert script.read_meminfo(StringIO(VALID_MEMINFO)) == (16191488, 9227472)


def test_read_meminfo_opens_only_fixed_proc_path(monkeypatch):
    opener = mock_open(read_data=VALID_MEMINFO)
    monkeypatch.setattr("builtins.open", opener)

    assert script.read_meminfo() == (16191488, 9227472)
    opener.assert_called_once_with("/proc/meminfo", "r", encoding="ascii")
