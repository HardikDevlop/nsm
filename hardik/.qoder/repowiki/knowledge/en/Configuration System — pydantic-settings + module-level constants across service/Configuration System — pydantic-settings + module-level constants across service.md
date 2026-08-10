---
kind: configuration_system
name: Configuration System — pydantic-settings + module-level constants across services
category: configuration_system
scope:
    - '**'
source_files:
    - backend/config/settings.py
    - backend/.env
    - icmp_discovery/config.py
    - frontend/vite.config.js
---

The repository implements configuration through two complementary approaches, one per service:

**Backend (FastAPI)** uses `pydantic_settings.BaseSettings` for typed, environment-driven configuration. The `backend/config/settings.py` module defines a `Settings` class with `SettingsConfigDict` pointing at `backend/.env`, loading UTF-8-encoded key-value pairs and ignoring unknown fields. Defaults are provided inline (e.g. `database_url`, `secret_key`, `access_token_expire_minutes`, `backend_cors_origins`) and the `.env` file under `backend/` overrides them at runtime. A cached `get_settings()` factory (`@lru_cache`) returns a singleton instance consumed by `main.py` to configure the FastAPI app title, CORS middleware origins, and other runtime behavior.

**ICMP Discovery Engine** uses plain Python module-level constants in `icmp_discovery/config.py`. All network, discovery, monitoring, reporting, file-path, console, and application metadata values are declared as top-level variables (e.g. `NETWORK_TARGET`, `TCP_PORTS`, `MONITOR_INTERVAL_SECONDS`, `JSON_FILE`, `APPLICATION_NAME`). These constants are imported directly by `app.py`, `main.py`, and discovery/monitoring modules. There is no env-file loader or validation layer; configuration changes require editing the source file.

**Frontend (Vite/React)** has no runtime configuration system beyond `vite.config.js`, which hard-codes the development proxy target (`http://127.0.0.1:5000`) for `/api` requests during local development. No `.env` files or build-time variable injection are used in the frontend.

**Key conventions observed:**
- Backend settings are strongly typed via Pydantic and loaded from a single `.env` file co-located with the settings module.
- Discovery engine configuration is static and colocated with the code that consumes it; there is no separation between config and code.
- Both services embed defaults directly in their configuration sources rather than relying on external config files for production.
- The backend exposes a `cors_origins` property that parses the comma-separated `backend_cors_origins` string into a list, demonstrating simple derived-field handling within the settings model.
- No feature flags, secret rotation, or multi-environment profiles are implemented beyond the `environment` setting string.