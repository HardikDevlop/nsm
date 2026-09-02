# Authentication and RBAC Runtime Verification

Date: 2026-08-29
Project: current NMS in `hardik`
Scope: read-only runtime verification. No users, roles, permissions, tokens, database rows, or application code were changed.

## Overall Result

**ENVIRONMENT ACCESS BLOCKED**

The supplied host-side result says `GET /api/v1/health = 200` and database connectivity is true. From this restricted execution environment, however, `127.0.0.1:8000` is not reachable. Therefore no authentication or RBAC claim is made from this environment.

The project source contains a default admin account declaration, but its password was not printed, sent, or included in this report. No mock credentials were created or used.

## Results

| Check | Endpoint/action | Result | HTTP status | Exact result |
|---|---|---|---|---|
| Backend reachability | `GET /api/v1/health` | NOT TESTABLE | 000 | `curl: (7) Couldn't connect to server` from restricted environment. |
| Valid login | `POST /api/v1/auth/login` | NOT TESTABLE | Not sent | Backend host was inaccessible; no credentials were sent. |
| JWT returned | Valid login response | NOT TESTABLE | Not received | Login could not be performed. No JWT was printed or stored in the report. |
| Invalid login rejection | `POST /api/v1/auth/login` with invalid credentials | NOT TESTABLE | Not sent | No request was sent because backend was inaccessible. |
| Authenticated identity | `GET /api/v1/auth/me` with valid token | NOT TESTABLE | Not sent | No valid token was available. |
| Unauthenticated protected API | `GET /api/v1/devices` without token | NOT TESTABLE | Not sent | Backend was inaccessible. |
| Authorized protected API | `GET /api/v1/devices` with valid token | NOT TESTABLE | Not sent | Backend was inaccessible. |
| Permission enforcement | Protected endpoint with insufficient permission | NOT TESTABLE | Not sent | Could not obtain a live role/token or call the endpoint. |
| Permission-denied case | Existing restricted role/user | NOT TESTABLE | Not sent | No existing restricted account was selected or modified. |

No check is marked `FAIL` because the application host is explicitly reported healthy outside this restricted environment; this runtime could not access that host.

## Reachability Command

Command:

```bash
curl --connect-timeout 3 --max-time 8 -sS \
  -D /tmp/nms-auth-headers \
  -o /tmp/nms-auth-health \
  -w 'url=http://127.0.0.1:8000/api/v1/health http=%{http_code} remote=%{remote_ip}\n' \
  http://127.0.0.1:8000/api/v1/health
```

Output:

```text
curl: (7) Couldn't connect to server
url=http://127.0.0.1:8000/api/v1/health http=000 remote=
```

This is classified as **ENVIRONMENT ACCESS BLOCKED**, not as proof that the host backend is down.

## Source-Confirmed Endpoint Paths

The backend source defines:

- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `GET /api/v1/health`

Protected device routes use permission dependencies, including `devices:read` and `devices:update`. Source presence is not treated as runtime verification.

## Safe Verification Procedure on the Host

Run these from the same network namespace/host where the healthy backend is running. Replace placeholders only with existing account credentials; do not print the password or token.

```bash
BASE=http://127.0.0.1:8000

curl -fsS "$BASE/api/v1/health"

curl -sS -o /tmp/login-response -w 'valid_login_http=%{http_code}\n' \
  -X POST "$BASE/api/v1/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"email":"<existing-account>","password":"<existing-password>"}'

# Extract the token in memory only, without printing it.
TOKEN="$(jq -r '.access_token' /tmp/login-response)"

curl -sS -o /tmp/me-response -w 'auth_me_http=%{http_code}\n' \
  -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/auth/me"

curl -sS -o /tmp/no-token-response -w 'no_token_http=%{http_code}\n' \
  "$BASE/api/v1/devices"

curl -sS -o /tmp/authorized-response -w 'authorized_http=%{http_code}\n' \
  -H "Authorization: Bearer $TOKEN" "$BASE/api/v1/devices"

unset TOKEN
```

For invalid login, use an intentionally invalid password only against the existing login endpoint and record the status/body without recording credentials. For permission denial, use an existing restricted role/user if one exists; do not create or alter accounts.

## Blocker

The restricted environment cannot access the host backend at `127.0.0.1:8000`. Authentication, JWT issuance, `/auth/me`, unauthenticated rejection, authorized access, and permission-denied enforcement remain unverified here.

