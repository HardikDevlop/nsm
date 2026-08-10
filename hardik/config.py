# Configuration
"""
----------------------------------------------------------
File Name: config.py
Purpose: Central configuration for the ICMP Discovery Service.
Description: Stores production-friendly defaults for network settings, ICMP behavior, logging, and output paths.
Dependencies: None
Author: Hardik Prajapati
Version: 1.0.0
----------------------------------------------------------
"""

from __future__ import annotations

# ==========================================================
# NETWORK CONFIGURATION
# ==========================================================

NETWORK_PREFIX: str = "192.168.100"
NETWORK_TARGET: str = f"{NETWORK_PREFIX}.0/24"
PING_COUNT: int = 1
PING_TIMEOUT: int = 1000
SCAN_INTERVAL: int = 15
MAX_WORKERS: int = 64
DISCOVERY_CHUNK_SIZE: int = 64

# ==========================================================
# DISCOVERY MODULE CONFIGURATION
# ==========================================================

TCP_PORTS: list[int] = [
    22,
    23,
    25,
    53,
    80,
    110,
    135,
    139,
    143,
    161,
    389,
    443,
    445,
    587,
    636,
    993,
    995,
    1433,
    1521,
    3306,
    3389,
    5432,
    5900,
    5985,
    5986,
    8080,
    8443,
    9100,
]
SOCKET_TIMEOUT_SECONDS: float = 0.75
HTTP_TIMEOUT_SECONDS: float = 1.25
SNMP_TIMEOUT_SECONDS: float = 0.8
WMI_TIMEOUT_SECONDS: int = 6
SNMP_COMMUNITIES: list[str] = ["public"]
ENABLE_SNMP_PROBES: bool = True
ENABLE_WMI_PROBES: bool = False
ENABLE_SSH_INVENTORY: bool = True

# ==========================================================
# MONITORING CONFIGURATION
# ==========================================================

MONITOR_INTERVAL_SECONDS: int = 60
SYSLOG_UDP_PORT: int = 5140
TRAP_UDP_PORT: int = 9162
EVENT_BUFFER_SIZE: int = 5000
ALERT_THRESHOLDS: dict[str, float] = {
    "packet_loss_percent": 20,
    "rtt_ms": 250,
    "cpu_percent": 85,
    "memory_percent": 85,
    "bandwidth_percent": 80,
    "temperature_celsius": 70,
    "power_status": 0,
}

# ==========================================================
# REPORT CONFIGURATION
# ==========================================================

SHOW_RAW_OUTPUT: bool = False
SHOW_PROGRESS: bool = True
SAVE_JSON: bool = True
SAVE_LOG: bool = True
CSV_OUTPUT: bool = True

# ==========================================================
# FILE LOCATIONS
# ==========================================================

JSON_FILE: str = "data/inventory.json"
CSV_FILE: str = "output/inventory.csv"
LOG_FOLDER: str = "data/logs/"

# ==========================================================
# CONSOLE CONFIGURATION
# ==========================================================

LINE: str = "=" * 70
SUB_LINE: str = "-" * 70

# ==========================================================
# APPLICATION INFORMATION
# ==========================================================

APPLICATION_NAME: str = "ICMP Discovery Service"
VERSION: str = "1.0.0"
AUTHOR: str = "Hardik Prajapati"
