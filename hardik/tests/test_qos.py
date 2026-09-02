from backend.api.qos_routes import QoSPayload, router
from backend.models import QoSSample
def test_qos_payload_validates_dscp_and_queue_fields():
    assert QoSPayload(device_id=1, observed_at="2026-01-01T00:00:00", dscp=46, queue_drops=2).dscp == 46
def test_qos_routes_and_history_model_exist():
    assert {r.path for r in router.routes} == {"/api/v1/qos/samples"}
    assert {"tos","dscp","phb","traffic_class","queue_utilization","queue_drops"}.issubset(QoSSample.__table__.columns.keys())
