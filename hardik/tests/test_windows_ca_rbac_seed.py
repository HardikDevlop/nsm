from backend import seed


def _extra_codes():
    return {f"{module}:{action}" for module, action in seed.EXTRA_PERMISSIONS}


def test_windows_ca_assign_is_registered_once():
    codes = [f"{module}:{action}" for module, action in seed.EXTRA_PERMISSIONS]
    assert codes.count("windows_ca:assign") == 1


def test_windows_ca_assign_is_reserved_for_full_privileged_roles():
    assert "windows_ca:assign" in _extra_codes()
    assert "windows_ca:assign" not in seed.OPERATOR_CODES
    assert "windows_ca:assign" not in seed.VIEWER_CODES


def test_seed_role_policy_gives_full_catalog_only_to_super_admin_and_admin():
    # seed.py passes None for both full-catalog roles; this is the established
    # policy that includes newly registered permissions idempotently.
    assert 'ensure_role("Super Admin", None' in open(seed.__file__, encoding="utf-8").read()
    assert 'ensure_role("Admin", None' in open(seed.__file__, encoding="utf-8").read()


def test_windows_ca_routes_require_assignment_permission():
    from pathlib import Path

    source = (Path(__file__).parents[1] / "backend/windows_monitoring/api.py").read_text(encoding="utf-8")
    assert 'require_permission("windows_ca:assign")' in source
    assert source.count('require_permission("windows_ca:assign")') >= 2
