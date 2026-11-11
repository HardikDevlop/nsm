# Security and RBAC Audit

## Confirmed in source

- JWT access tokens use `python-jose` and HS256; passwords use bcrypt through passlib.
- Production settings reject placeholder/short `SECRET_KEY` and missing credential-encryption key.
- Device credentials are designed for Fernet encryption (`utils/crypto.py` and settings).
- Role authority and permission helpers enforce hierarchy; protected Super Admin and Admin audit visibility are explicit.
- Site scope is represented by user-site assignments and `can_access_site`; SNMP routes declare a site-scope dependency.
- SSH host-key scan/trust/revoke services exist.
- Windows CA bundles and effective trust are modeled separately; callers do not supply the server trust anchor.
- Authenticated WebSocket terminal access is implemented as a session-specific endpoint.
- Audit-log models/services and frontend views exist.

## Risks/limitations requiring follow-up

- Development defaults include a localhost PostgreSQL URL with a visible default password and a placeholder secret; production validation mitigates this only when `environment=production` is actually set.
- HS256 centralizes token trust in one secret; key rotation/issuer/audience policy is not evident.
- Telnet is inherently plaintext and should be restricted or deprecated operationally.
- Site isolation is not uniformly proven for every feature by static inspection; legacy and nullable site records need endpoint-by-endpoint review.
- CORS origins are configurable, but transport TLS/reverse-proxy enforcement is not defined in repository deployment artifacts.
- Secrets must be reviewed in environment handling; this audit intentionally did not expose values.

No penetration test, brute force, network scan, live credential test, or TLS validation was performed.

