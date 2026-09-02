from backend.api.config_compliance_routes import router
from backend.models import ConfigurationCompliancePolicy, ConfigurationComplianceViolation

def test_compliance_models_store_rules_and_violation_history():
    assert "rules" in ConfigurationCompliancePolicy.__table__.c
    assert "evidence" in ConfigurationComplianceViolation.__table__.c
    assert "recommendation" in ConfigurationComplianceViolation.__table__.c

def test_compliance_routes_are_read_only_until_explicit_evaluation():
    paths = {route.path for route in router.routes}
    assert "/api/v1/config-compliance/policies" in paths
    assert "/api/v1/config-compliance/evaluate" in paths
    assert "/api/v1/config-compliance/violations" in paths
