from datetime import datetime

from backend.flow.correlation import FlowCorrelationResolver
from backend.flow.models import NormalizedFlow


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows


class _Db:
    def __init__(self):
        self.devices = {
            "192.0.2.10": {"id": 10, "hostname": "Core-switch"},
            "192.0.2.20": {"id": 20, "hostname": "Edge-switch"},
        }
        self.interfaces = {
            10: {15: "GigabitEthernet1/0/15"},
            20: {15: "GigabitEthernet2/0/15"},
        }
        self.queries = 0

    def execute(self, statement, params):
        self.queries += 1
        sql = str(statement)
        if "FROM devices" in sql:
            device = self.devices.get(params["exporter_ip"])
            return _Result([device] if device else [])
        if "FROM latest_interface" in sql:
            rows = [
                {"if_index": index, "name": self.interfaces[params["device_id"]][index]}
                for index in params["if_indexes"]
                if index in self.interfaces.get(params["device_id"], {})
            ]
            return _Result(rows)
        raise AssertionError(f"unexpected query: {sql}")


def _flow(protocol: str, exporter_ip: str, if_index: int = 15) -> NormalizedFlow:
    now = datetime(2026, 1, 1)
    return NormalizedFlow(exporter_ip, protocol, now, now, now,
                          input_interface_id=if_index, output_interface_id=if_index)


def test_known_exporter_and_interface_are_correlated():
    db = _Db()
    flow = _flow("sflow", "192.0.2.10")
    FlowCorrelationResolver().correlate(db, [flow])
    assert flow.device_id == 10
    assert flow.raw_fields["correlation"] == {
        "device_name": "Core-switch",
        "input_ifindex": 15,
        "input_interface_name": "GigabitEthernet1/0/15",
        "output_ifindex": 15,
        "output_interface_name": "GigabitEthernet1/0/15",
    }


def test_unknown_exporter_keeps_device_null():
    flow = _flow("ipfix", "192.0.2.99")
    FlowCorrelationResolver().correlate(_Db(), [flow])
    assert flow.device_id is None
    assert flow.raw_fields["correlation"]["input_interface_name"] is None


def test_unknown_ifindex_keeps_interface_name_null():
    db = _Db()
    flow = _flow("ipfix", "192.0.2.10", if_index=999)
    FlowCorrelationResolver().correlate(db, [flow])
    assert flow.device_id == 10
    assert flow.raw_fields["correlation"]["input_interface_name"] is None


def test_same_ifindex_is_scoped_by_resolved_device():
    db = _Db()
    flows = [_flow("sflow", "192.0.2.10"), _flow("ipfix", "192.0.2.20")]
    FlowCorrelationResolver().correlate(db, flows)
    assert [flow.device_id for flow in flows] == [10, 20]
    assert [flow.raw_fields["correlation"]["input_interface_name"] for flow in flows] == [
        "GigabitEthernet1/0/15", "GigabitEthernet2/0/15"
    ]


def test_sflow_and_ipfix_use_the_same_resolver():
    db = _Db()
    flows = [_flow("sflow", "192.0.2.10"), _flow("ipfix", "192.0.2.10")]
    resolver = FlowCorrelationResolver()
    resolver.correlate(db, flows)
    assert all(flow.device_id == 10 for flow in flows)
    assert all(flow.raw_fields["correlation"]["output_interface_name"] == "GigabitEthernet1/0/15" for flow in flows)


def test_resolver_caches_exporter_and_interface_lookups():
    db = _Db()
    resolver = FlowCorrelationResolver()
    resolver.correlate(db, [_flow("sflow", "192.0.2.10")])
    first_queries = db.queries
    resolver.correlate(db, [_flow("ipfix", "192.0.2.10")])
    assert db.queries == first_queries
