from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException

from backend.api.routes import clear_all_alerts


def _user(role_name: str, level: int, system: bool = True):
    return SimpleNamespace(role=SimpleNamespace(role_name=role_name, authority_level=level, is_system_role=system), id=1)


def test_clear_all_allows_super_admin_with_alert_delete_permission():
    db = Mock()
    db.query.return_value.filter.return_value.update.return_value = 3
    with patch("backend.api.routes.is_super_admin", return_value=True), patch("backend.api.routes.audit"):
        result = clear_all_alerts(db, _user("Super Admin", 100))
    assert result == {"cleared": 3}
    db.commit.assert_called_once()


@pytest.mark.parametrize("user", [_user("Admin", 80), _user("Operator", 40), SimpleNamespace(role=None, id=1)])
def test_clear_all_rejects_non_global_users(user):
    with patch("backend.api.routes.is_super_admin", return_value=False):
        with pytest.raises(HTTPException) as exc:
            clear_all_alerts(Mock(), user)
    assert exc.value.status_code == 403
