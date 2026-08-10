# Helper Functions
"""
----------------------------------------------------------
File Name: utils.py
Purpose: Common utility helpers for the ICMP Discovery Service.
Description: Provides IP generation, IP validation, timestamping, directory/file helpers, timing, and countdown utilities.
Dependencies: json, os, socket, time, datetime, config
Author: Hardik Prajapati
Version: 1.0.0
----------------------------------------------------------
"""

from __future__ import annotations

import json
import os
import socket
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from config import JSON_FILE


def generate_ips(network_prefix: str) -> List[str]:
    """Generate all IPs in a /24 subnet for the supplied prefix.

    Args:
        network_prefix: The first three octets of the subnet, e.g. 192.168.100.

    Returns:
        A list of IP addresses from .1 through .255.

    Raises:
        ValueError: If the prefix is empty.
    """
    if not network_prefix:
        raise ValueError("network_prefix must not be empty")
    return [f"{network_prefix}.{i}" for i in range(1, 256)]


def is_valid_ip(ip: str) -> bool:
    """Validate whether the supplied string is a valid IPv4 address."""
    try:
        socket.inet_aton(ip)
        return True
    except OSError:
        return False


def current_time() -> str:
    """Return the current local timestamp as a string."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class ScanTimer:
    """Measure elapsed time for scan operations."""

    def __init__(self) -> None:
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None

    def start(self) -> None:
        """Start the timer."""
        self.start_time = time.perf_counter()

    def stop(self) -> None:
        """Stop the timer."""
        self.end_time = time.perf_counter()

    @property
    def elapsed(self) -> float:
        """Return the elapsed time in seconds."""
        if self.start_time is None:
            return 0.0
        if self.end_time is None:
            return round(time.perf_counter() - self.start_time, 3)
        return round(self.end_time - self.start_time, 3)


def create_directory(path: str) -> None:
    """Create a directory if it does not already exist."""
    os.makedirs(path, exist_ok=True)


def save_json(data: Dict[str, Any]) -> None:
    """Persist a dictionary payload to the configured JSON file."""
    folder = os.path.dirname(JSON_FILE)
    if folder:
        create_directory(folder)
    with open(JSON_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=4)


def load_json() -> Dict[str, Any]:
    """Load JSON data from the configured JSON file if present."""
    if not os.path.exists(JSON_FILE):
        return {}
    try:
        with open(JSON_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except (json.JSONDecodeError, OSError):
        return {}


def countdown(seconds: int) -> None:
    """Print a countdown for the next scan cycle."""
    for remaining in range(seconds, 0, -1):
        print(f"\rNext Scan Starts In : {remaining:02d} sec", end="")
        time.sleep(1)
    print()
