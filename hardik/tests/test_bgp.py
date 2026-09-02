from backend.api.bgp_routes import BGPObservationPayload,router
from backend.models import BGPObservation
def test_bgp_payload_preserves_neighbor_route_fields():
 x=BGPObservationPayload(device_id=1,neighbor='192.0.2.2',state='established',remote_as=64512,next_hop='192.0.2.2',prefixes=4,as_path='64512 64513',observed_at='2026-01-01T00:00:00');assert x.remote_as==64512
def test_bgp_history_model_and_routes():
 assert {'neighbor','state','remote_as','next_hop','prefixes','as_path'}.issubset(BGPObservation.__table__.columns.keys());assert {r.path for r in router.routes}=={'/api/v1/bgp/observations','/api/v1/bgp/neighbors'}
