# Current Authorization Baseline

Source: `test_authorization_baseline.py`

Result: **20 passed, 0 failed**

This document records current behavior only. “Future Expected” describes the
intended hierarchical and scoped authorization model; it is not implemented.

| Role | Resource | Action | Current Result | Future Expected |
|---|---|---|---|---|
| Admin | Users | Read | ALLOWED (`users:read`) | ALLOWED within authority and scope |
| Admin | Users | Create | ALLOWED (`users:create`) | Manage only lower-authority users |
| Admin | Users | Update | ALLOWED for lower users; Admin target is denied | Lower-authority users only |
| Admin | Users | Delete | Permission exists; Admin targets are protected by current literal-name check | Lower-authority users only |
| Operator | Users | Read | DENIED (403) | DENIED |
| Operator | Users | Create/update/delete | DENIED by current seeded permissions | Operational users cannot manage users |
| Viewer | Users | Read/create/update/delete | DENIED (403) | DENIED |
| Admin | Roles | Read | ALLOWED (`roles:read`) | ALLOWED within authority limits |
| Admin | Roles | Create/update/delete | ALLOWED (`roles:create/update/delete`) | Cannot create or modify equal/higher roles |
| Operator | Roles | Read/create/update/delete | DENIED (403) | DENIED |
| Viewer | Roles | Read/create/update/delete | DENIED (403) | DENIED |
| Admin | Permissions | Read | ALLOWED (`permissions:read`) | ALLOWED for authorized administrators |
| Admin | Permissions | Create/update/delete | ALLOWED (`permissions:create/update/delete`) | Cannot grant permissions above own authority |
| Operator | Permissions | Read/create/update/delete | DENIED (403) | DENIED |
| Viewer | Permissions | Read/create/update/delete | DENIED (403) | DENIED |
| Admin | Sites | Read | ALLOWED | ALLOWED within assigned scope |
| Admin | Sites | Manage | ALLOWED through site CRUD permissions | ALLOWED within assigned scope |
| Operator | Sites | Read | ALLOWED | ALLOWED within assigned scope |
| Operator | Sites | Manage | DENIED by current seeded permissions | DENIED unless explicitly delegated |
| Viewer | Sites | Read | ALLOWED | ALLOWED within assigned scope |
| Viewer | Sites | Manage | DENIED | DENIED |
| Admin | Devices | Read | ALLOWED | ALLOWED within assigned scope |
| Admin | Devices | Create/update/delete | ALLOWED | ALLOWED within assigned scope |
| Operator | Devices | Read | ALLOWED | ALLOWED only on assigned devices/sites |
| Operator | Devices | Create/update | ALLOWED | Only where explicitly permitted and scoped |
| Operator | Devices | Delete | DENIED by current seeded permissions | DENIED unless explicitly delegated and scoped |
| Viewer | Devices | Read | ALLOWED | ALLOWED only on assigned devices/sites |
| Viewer | Devices | Create/update/delete | DENIED | DENIED |
| Admin | Audit Logs | Read | ALLOWED (`audit_logs:read`) | ALLOWED according to authority scope |
| Operator | Audit Logs | Read | ALLOWED (`audit_logs:read`) | Limited to permitted scope; not security-wide by default |
| Viewer | Audit Logs | Read | ALLOWED (`audit_logs:read`) | Limited read-only visibility according to policy |
| Any role | Audit Logs | Update/delete | No public route exposed; baseline returns 405 | Append-only and database-protected |

## Confirmed risks

### Privilege escalation

- Admin can replace a role’s permissions through `PUT /api/v1/roles/{id}/permissions`.
- There is no authority-level check preventing an administrator from granting powerful permissions to another role.
- Role and permission management is permission-based, not hierarchy-based.

### Cross-site access

- The test data contains Site A/Device A and Site B/Device B.
- An Operator with `devices:read` can directly read Site B’s device by ID.
- An Operator with `devices:update` can directly update Site B’s device by ID.
- User-site and user-device assignments do not yet exist, so backend object scope is not enforced.

### Admin-to-Admin restrictions

- Updating another user whose role name is exactly `Admin` is currently denied.
- This is a literal role-name protection, not a general authority hierarchy.
- The intended future rule is broader: an Admin must not modify, delete, promote, demote, block, or grant permissions to an equal- or higher-authority user.

## Scope

This is a pre-change baseline. It intentionally documents existing behavior and
does not represent implemented future protections.
