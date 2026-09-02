"""Optional real-device SNMP integration test.

This file is never run against a device unless explicitly enabled with
NMS_SNMP_INTEGRATION=1 and the required environment variables.
"""

import os

import pytest

from backend.snmp.collector import SNMPService
from backend.snmp.credentials import SNMPCredentials


@pytest.mark.skipif(
    os.getenv("NMS_SNMP_INTEGRATION") != "1",
    reason="Set NMS_SNMP_INTEGRATION=1 to run real-device SNMP integration tests",
)
def test_real_device_full_poll_is_opt_in():
    host = os.environ["NMS_SNMP_HOST"]
    version = os.getenv("NMS_SNMP_VERSION", "v2c")
    credentials = SNMPCredentials(
        version=version,
        community=os.getenv("NMS_SNMP_COMMUNITY", "public"),
        username=os.getenv("NMS_SNMP_USERNAME"),
        auth_protocol=os.getenv("NMS_SNMP_AUTH_PROTOCOL"),
        auth_password=os.getenv("NMS_SNMP_AUTH_PASSWORD"),
        privacy_protocol=os.getenv("NMS_SNMP_PRIVACY_PROTOCOL"),
        privacy_password=os.getenv("NMS_SNMP_PRIVACY_PASSWORD"),
        security_level=os.getenv("NMS_SNMP_SECURITY_LEVEL"),
    )

    result = SNMPService(credentials, timeout=2.0, retries=1).collect(host)

    assert result["ip"] == host
    assert "collectors" in result
