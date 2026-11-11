import base64

import pytest

from backend.config.settings import Settings


def encoded_key(seed: bytes = b"k") -> str:
    return base64.urlsafe_b64encode(seed * 32).decode().rstrip("=")


def test_challenge_signing_is_disabled_by_default():
    settings = Settings(_env_file=None)
    assert settings.windows_helper_challenge_keys == ""
    assert settings.windows_helper_challenge_active_key_id == ""
    assert settings.windows_helper_challenge_key_map == {}
    assert settings.windows_helper_challenge_active_key is None


def test_active_and_previous_keys_are_decoded_without_exposing_material():
    active = encoded_key(b"a")
    previous = encoded_key(b"b")
    settings = Settings(
        _env_file=None,
        windows_helper_challenge_keys=f"active={active},previous={previous}",
        windows_helper_challenge_active_key_id="active",
    )
    assert settings.windows_helper_challenge_key_map == {"active": b"a" * 32, "previous": b"b" * 32}
    assert settings.windows_helper_challenge_active_key == b"a" * 32


@pytest.mark.parametrize("kwargs", [
    {"windows_helper_challenge_active_key_id": "active"},
    {"windows_helper_challenge_keys": f"active={encoded_key() }"},
    {"windows_helper_challenge_keys": f"active={encoded_key()},active={encoded_key(b'x')}" , "windows_helper_challenge_active_key_id": "active"},
    {"windows_helper_challenge_keys": "active=not-base64", "windows_helper_challenge_active_key_id": "active"},
    {"windows_helper_challenge_keys": f"active={base64.urlsafe_b64encode(b'x' * 31).decode().rstrip('=')}", "windows_helper_challenge_active_key_id": "active"},
    {"windows_helper_challenge_keys": f"active={encoded_key()}", "windows_helper_challenge_active_key_id": "missing"},
])
def test_invalid_challenge_configuration_is_rejected_without_secret_disclosure(kwargs):
    secret = next((value for value in kwargs.values() if isinstance(value, str) and "=" in value), "secret-material")
    with pytest.raises(ValueError) as error:
        Settings(_env_file=None, **kwargs)
    assert secret not in str(error.value)
