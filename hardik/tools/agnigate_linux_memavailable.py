#!/usr/bin/env python3
"""Print Linux effective-memory values for a future Net-SNMP extend entry."""

from __future__ import annotations

import re
import sys
from typing import TextIO


MEMINFO_PATH = "/proc/meminfo"
_MEMINFO_LINE = re.compile(r"^([A-Za-z][A-Za-z0-9_]*(?:\([A-Za-z0-9_]+\))?)\s*:\s*(-?[0-9]+)(?:\s+(\S+))?\s*$")
_REQUIRED_KEYS = frozenset(("MemTotal", "MemAvailable"))


def parse_meminfo(text: str) -> tuple[int, int]:
    """Return (MemTotalKiB, MemAvailableKiB) from strict meminfo text."""
    if not isinstance(text, str):
        raise ValueError("meminfo content must be text")

    values: dict[str, tuple[int, str | None]] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        match = _MEMINFO_LINE.fullmatch(line)
        if match is None:
            raise ValueError("malformed meminfo line")
        key, raw_value, unit = match.groups()
        if key in values:
            raise ValueError("duplicate meminfo key")
        values[key] = (int(raw_value), unit)

    if not _REQUIRED_KEYS.issubset(values):
        raise ValueError("required meminfo key missing")

    total, total_unit = values["MemTotal"]
    available, available_unit = values["MemAvailable"]
    if total_unit != "kB" or available_unit != "kB":
        raise ValueError("required meminfo value has invalid unit")
    if total <= 0 or available < 0 or available > total:
        raise ValueError("required meminfo values are out of range")
    return total, available


def read_meminfo(stream: TextIO | None = None) -> tuple[int, int]:
    """Read only the fixed kernel meminfo path unless a test stream is given."""
    if stream is not None:
        return parse_meminfo(stream.read())
    with open(MEMINFO_PATH, "r", encoding="ascii") as handle:
        return parse_meminfo(handle.read())


def main(argv: list[str] | None = None) -> int:
    """Emit exactly one response line, or a generic error on stderr."""
    args = sys.argv[1:] if argv is None else argv
    if args:
        print("meminfo extension does not accept arguments", file=sys.stderr)
        return 2
    try:
        total, available = read_meminfo()
    except (OSError, UnicodeError, ValueError, OverflowError):
        print("unable to read valid Linux memory information", file=sys.stderr)
        return 1
    print(f"version=1 MemTotalKiB={total} MemAvailableKiB={available}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
