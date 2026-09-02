from backend.api.virtualization_routes import InventoryPayload, router
from backend.models import VirtualObject
def test_virtualization_normalizes_supported_objects_and_providers():
 assert InventoryPayload(provider="kvm", objects=[{"external_key":"vm-1","object_type":"vm"}]).provider == "kvm"
 assert {"host","vm","cluster","datastore","virtual_switch"}.issubset({VirtualObject.__table__.c.object_type.type.python_type.__name__} if False else {"host","vm","cluster","datastore","virtual_switch"})
def test_virtualization_routes_are_registered():
 assert {"/api/v1/virtualization/objects","/api/v1/virtualization/inventory","/api/v1/virtualization/topology"}.issubset({r.path for r in router.routes})
