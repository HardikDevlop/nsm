from backend.api import routes
from backend.config.settings import Settings


def test_branding_settings_filter_unknown_themes():
    settings = Settings(branding_allowed_themes="light,unknown,dark")

    assert settings.allowed_themes == ["light", "dark"]


def test_branding_endpoint_returns_backend_configuration(monkeypatch):
    monkeypatch.setattr(
        routes,
        "get_settings",
        lambda: Settings(
            branding_application_name="Customer NMS",
            branding_logo_url="https://cdn.example.test/logo.svg",
            branding_allowed_themes="dark",
        ),
    )

    result = routes.get_branding()

    assert result.application_name == "Customer NMS"
    assert result.logo_url == "https://cdn.example.test/logo.svg"
    assert result.allowed_themes == ["dark"]
