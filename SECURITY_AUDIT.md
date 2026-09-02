# NMS Security Audit

Date: 2026-08-29  
Scope: read-only application security review  
Repository: `/home/agnigate/Desktop/NMS`  
Certification status: this is an engineering review, not a certification or
compliance assessment.

## Executive Summary

The backend uses FastAPI dependency-based authentication/RBAC, bcrypt password
hashing, signed JWTs, SQLAlchemy/bound parameters for normal data values,
encrypted credential/configuration storage, and bounded SNMP operation
timeouts. The frontend uses bearer-token API calls and React rendering without
the reviewed `dangerouslySetInnerHTML`/`innerHTML` sinks.

The most urgent issue is credential hygiene: the repository contains a seeded
default administrator password and insecure fallback database/JWT secrets in
source configuration. These must be removed or made deployment-blocking before
production use. Runtime validation was limited because PostgreSQL, the backend,
and the frontend were unavailable during this audit.

## Severity Scale

- **Critical:** likely immediate compromise or unrestricted administrative
  access.
- **High:** serious compromise risk or security control bypass if deployed in
  a typical environment.
- **Medium:** meaningful defense-in-depth or authorization/data-exposure risk.
- **Low:** hardening, observability, or operational risk.
- **Informational:** no direct vulnerability found; improvement recommended.

## Findings

### SEC-01: Hardcoded default administrator credentials

**Severity: Critical**  
**Evidence:** `hardik/backend/seed.py:197-208` creates
`admin@gmail.com` with a fixed password when the user does not exist.

If the seeded account survives deployment, anyone who knows the repository or
default documentation can attempt administrative login. The account is given
the Admin role and the seed path runs during application startup.

**Remediation:**

- Remove the fixed password from source.
- Require a one-time bootstrap secret supplied through a secret manager, or
  create the initial administrator through an out-of-band provisioning command.
- Force password rotation/disablement on first login.
- Do not print or document a usable default credential.
- Add a test that production startup fails when bootstrap credentials are not
  explicitly configured.

### SEC-02: Insecure fallback secrets and database credentials

**Severity: High**  
**Evidence:** `hardik/backend/config/settings.py:14-20` contains fallback
values for the PostgreSQL URL, database password, and JWT `secret_key`.

If environment configuration is missing or misloaded, JWT signing can use a
predictable key and the application can attempt a known database credential.
`hardik/backend/utils/crypto.py:9-16` also derives the Fernet key from that
JWT secret when `CREDENTIAL_ENCRYPTION_KEY` is empty, coupling two security
domains and making encrypted data dependent on a potentially weak fallback.

**Remediation:**

- Remove production-usable secret/database fallbacks.
- Validate secret length/entropy and require explicit values when
  `ENVIRONMENT=production`.
- Require a dedicated credential-encryption key; never derive it from the JWT
  signing secret in production.
- Rotate any secrets that may have been used outside a disposable environment.
- Keep `.env` files outside version control and use a secret manager.

### SEC-03: JWT access token is stored in browser localStorage

**Severity: High**  
**Evidence:** `figma design/src/lib/api.ts:29-40` and login/logout paths store
`nms_access_token` in `window.localStorage`.

Any successful XSS in the frontend origin can read the token and replay it.
The current React source did not show an obvious HTML injection sink, which
reduces but does not eliminate this risk.

**Remediation:**

- Prefer a short-lived access token in memory plus a rotated refresh token in
  a `Secure`, `HttpOnly`, `SameSite` cookie.
- If localStorage must remain for compatibility, shorten token lifetime,
  rotate/revoke tokens, add a strict CSP, and audit every third-party asset and
  HTML rendering path.
- Add browser tests for logout, token expiry, and cross-tab token handling.

### SEC-04: No explicit HTTPS/security-header enforcement in the FastAPI app

**Severity: Medium**  
**Evidence:** `hardik/backend/main.py:88-94` configures CORS but does not add
HTTPS redirect, trusted-host validation, HSTS, CSP, frame protection, or
content-type protection middleware.

The deployment guide may provide a reverse proxy, but the application itself
does not enforce or document these controls at the code boundary. A direct or
misconfigured deployment could expose credentials and permit browser hardening
gaps.

**Remediation:**

- Terminate TLS at a controlled proxy and enforce HTTPS for production.
- Add trusted-host and security-header middleware or prove equivalent proxy
  configuration in deployment checks.
- Use HSTS only after HTTPS is consistently available.
- Define a CSP compatible with the Vite build and external branding assets.
- Add a deployment test that checks headers and rejects unexpected hosts.

### SEC-05: Tenant/organization authorization is not enforced as a security scope

**Severity: Medium**  
**Evidence:** `Organization` exists in `hardik/backend/models/__init__.py`, but
`User` has no organization/tenant relationship. Many protected APIs authorize
only by global permission, not by organization/site ownership.

An authenticated user with a permission may be able to read or mutate records
belonging to another organization if multi-tenant deployment is assumed.
Backend branding is also currently global configuration rather than a scoped
tenant record.

**Remediation:**

- Define the tenant boundary explicitly: single-tenant deployment or enforced
  organization scope.
- Add organization claims/relations and apply scope predicates to every device,
  site, alert, incident, CMDB, APM, flow, and report query.
- Test cross-tenant read, update, delete, export, and live-poll denial cases.

### SEC-06: Configuration attachment API does not own or validate file storage

**Severity: Medium**  
**Evidence:** incident attachments accept a caller-controlled `storage_key`
and metadata in `hardik/backend/api/incident_routes.py:41-47,145`, rather than
performing a controlled upload and storage operation.

The API does not establish ownership, malware scanning, path isolation,
content-size verification against actual bytes, or safe download authorization.
If a future download endpoint treats `storage_key` as a filesystem path, path
traversal and unauthorized file access become possible.

**Remediation:**

- Use server-managed object keys, never caller-selected filesystem paths.
- Validate actual upload size/type, scan content, encrypt sensitive files, and
  authorize every download by incident and tenant.
- Do not execute or render uploaded content inline; use safe content
  disposition and an allowlisted content-type policy.
- Add traversal, oversized-file, spoofed-content-type, and cross-tenant tests.

### SEC-07: Syslog receiver is bindable on all interfaces without lifecycle/security policy

**Severity: Medium**  
**Evidence:** `hardik/backend/syslog/__init__.py:23-28` binds UDP/TCP receivers
to `0.0.0.0` by default and does not show TLS, source ACLs, rate limiting,
message-size limits, or authentication. The receiver is not currently started
from `backend/main.py`, which reduces current exposure but also means runtime
behavior is not verified.

**Remediation:**

- Bind only to an explicitly configured interface/port.
- Add TCP TLS where required, source allowlists, datagram/message limits,
  bounded queue metrics, and rate/connection limits.
- Treat logs as untrusted input and keep regex correlation rules bounded.
- Start the receiver only through explicit application lifecycle/configuration
  and add network-level tests.

### SEC-08: Log and telemetry redaction is not demonstrated for sensitive values

**Severity: Medium**  
**Evidence:** SNMP diagnostics log device IPs and usernames in
`hardik/backend/api/snmp_device_routes.py:671`, while the application includes
credential/configuration and telemetry pipelines. The reviewed logs do not
show a centralized redaction filter.

Usernames, IPs, raw fields, exception text, or future vendor payloads can be
sensitive in an operational environment. Configuration content must never be
logged.

**Remediation:**

- Add structured logging with an explicit allowlist of fields.
- Redact passwords, communities, auth/privacy keys, tokens, configuration
  bodies, request headers, and arbitrary raw telemetry.
- Avoid f-strings for security-sensitive logs and define retention/access
  controls for log sinks.
- Add tests that submit sensitive values and assert they are absent from logs.

### SEC-09: Regex/query input resource exhaustion needs limits and execution policy

**Severity: Low/Medium**  
**Evidence:** Syslog correlation rules accept caller-supplied regex patterns
(`hardik/backend/api/syslog_routes.py:18-22`) and evaluate them with
`re.search` in `hardik/backend/syslog/__init__.py:43-46`.

Python regular expressions can be vulnerable to catastrophic backtracking.
The API limits pattern length but does not restrict regex complexity or
execution time.

**Remediation:**

- Use a safe-regex engine or restrict rules to an audited pattern language.
- Compile/validate rules on write and reject unsafe constructs.
- Bound message length and evaluation work per record.
- Add adversarial-pattern tests and a per-rule execution budget.

### SEC-10: CORS is configurable but requires production validation

**Severity: Low/Medium**  
**Evidence:** `hardik/backend/main.py:88-94` enables credentials and all
methods/headers, while origins come from configuration. The current local
`.env` origins were non-wildcard, but no live header test was possible.

This is not an automatic vulnerability when origins are tightly controlled,
but an accidental wildcard or untrusted origin combined with credentials can
create cross-origin exposure.

**Remediation:**

- Reject `*` whenever `allow_credentials=True`.
- Use a strict production origin allowlist and separate development settings.
- Limit methods and headers to the API requirements.
- Add automated preflight tests for approved and rejected origins.

## Reviewed Areas With No Direct Vulnerability Found

### Authentication and password storage

Password verification uses Passlib bcrypt in `backend/auth/security.py`.
JWTs validate signature, algorithm, and expiration. Remaining risks are the
default credentials/secrets above, long default token lifetime, and lack of
observed live token revocation/rotation testing.

### RBAC and API authorization

Protected routes consistently use `require_permission(...)` or
`require_any_permission(...)` in the reviewed route modules. This supports
least privilege at the permission level. Tenant/resource-level authorization
and live allow/deny behavior remain unverified.

### SQL injection

Reviewed SQLAlchemy filters use bound parameters. Dynamic SQL was found for
allowlisted analytics dimensions, migration identifiers, and a fixed internal
device-owned table list. No user-controlled SQL identifier interpolation was
identified in the reviewed paths. Continue to preserve allowlists and bound
parameters when adding endpoints.

### XSS

The reviewed frontend search found no `dangerouslySetInnerHTML`, direct
`innerHTML`, `document.write`, `eval`, or `new Function` usage. React escaping
therefore provides the normal baseline. This does not replace a browser scan
or review of future HTML/markdown rendering and external logo URLs.

### CSRF

The current API uses bearer headers rather than ambient authentication cookies,
so classic cookie CSRF is reduced. If authentication moves to cookies, add
SameSite and CSRF-token/origin protections before enabling state-changing
requests.

### Command execution

Local-subnet detection uses fixed command names and argument arrays with
`subprocess.run`, timeouts, and no `shell=True` in the reviewed path. Continue
to validate interface names and avoid passing shell strings.

### SNMP credential storage

SNMP community/auth/privacy values are encrypted through Fernet before
persistence in the reviewed discovery path. Encryption key management and
production secret requirements remain dependent on SEC-02. Never return
decrypted credentials through API responses or logs.

## Runtime and Test Limitations

- PostgreSQL at `127.0.0.1:5432` was unavailable.
- Backend port `8000` and frontend port `5173` were unavailable.
- Full backend pytest collection was blocked by missing `hypothesis`.
- Available SNMP/collector unit tests passed (`292 passed`).
- Frontend tests passed (`16 passed`) and the production build passed.
- No dynamic DAST, dependency vulnerability scan, browser security scan,
  authenticated API penetration test, TLS scan, or production log review was
  performed.

## Prioritized Remediation Plan

1. Remove default admin credentials and insecure secret/database fallbacks;
   enforce production secret validation and rotate exposed values.
2. Establish the deployment TLS/security-header/CORS baseline.
3. Define and enforce organization/tenant data scope if multi-tenancy is
   required.
4. Replace localStorage JWT persistence or add compensating CSP/token controls.
5. Harden incident attachments and Syslog receiver boundaries before enabling
   them in production.
6. Add structured secret redaction and adversarial regex tests.
7. Restore PostgreSQL/test dependencies and run authenticated integration,
   browser, dependency, and DAST checks in an isolated environment.

No certifications, compliance attestations, or security guarantees are claimed
by this report.
