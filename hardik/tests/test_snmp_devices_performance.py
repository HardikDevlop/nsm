import inspect

from backend.api import snmp_device_routes
from backend.models import Device, DeviceCredential
from backend.models.identity import DeviceIdentity
from backend.models.snmp import MonitoringConfig


class _Query:
    def __init__(self, db, rows):
        self.db = db
        self.rows = rows

    def select_from(self, *models):
        return self

    def outerjoin(self, *args, **kwargs):
        return self

    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def all(self):
        self.db.all_calls += 1
        return self.rows


class _MetadataSession:
    def __init__(self, rows):
        self.rows = rows
        self.all_calls = 0

    def query(self, *models):
        self.query_models = models
        return _Query(self, self.rows)


def test_device_list_metadata_uses_one_batched_query_and_preserves_rows():
    credential = DeviceCredential(device_id=7, snmp_version="v3")
    credential.id = 1
    identity = DeviceIdentity(device_id=7, vendor="Example", sys_name="edge-01")
    identity.id = 1
    first_config = MonitoringConfig(device_id=7, module_name="cpu", enabled=True, status="running")
    first_config.id = 10
    second_config = MonitoringConfig(device_id=7, module_name="interfaces", enabled=False, status="stopped")
    second_config.id = 11
    rows = [
        (credential, identity, first_config),
        (credential, identity, first_config),
        (credential, identity, second_config),
    ]
    db = _MetadataSession(rows)

    credentials, identities, configs = snmp_device_routes._load_device_list_metadata(
        db, [7], DeviceIdentity, MonitoringConfig,
    )

    assert db.all_calls == 1
    assert credentials[7] is credential
    assert identities[7] is identity
    assert configs[7] == [first_config, second_config]


def test_device_list_keeps_pagination_and_filter_parameters():
    parameters = inspect.signature(snmp_device_routes.list_snmp_devices_optimized).parameters
    assert parameters["page"].default.default == 1
    assert parameters["page_size"].default.default == 50
    for name in ("search", "status", "snmp_status", "monitoring_status", "device_type", "vendor", "model", "hostname", "sort_by", "sort_order"):
        assert name in parameters
