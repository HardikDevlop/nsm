# ICMP Probe Capability Fix / Verification Report

**Date:** 2026-09-17 (Asia/Kolkata)  
**Scope:** worker → probe only. No database status, health, SNMP, scheduler, topology, or mock-data changes were made.

## Result

The actual NMS backend execution context could not be reached from this workspace. No backend process, NMS systemd unit, Docker container, supervisor process, or frontend process was running at inspection time. The tests below ran in the managed Codex shell, not in the production service namespace.

Because the production context is unavailable, no capability or code fix was applied. This report must not be interpreted as proof that the Ubuntu NMS host has the same permissions.

## Required fields

- **BACKEND EXECUTION CONTEXT:** NOT OBSERVED; no running FastAPI/backend process, systemd unit, or container
- **BACKEND PID:** NOT AVAILABLE
- **BACKEND USER:** NOT AVAILABLE; local diagnostic shell user was `agnigate` (UID 1000)
- **PYTHON EXECUTABLE TESTED:** `/usr/bin/python3`
- **VIRTUALENV:** NOT AVAILABLE
- **WORKING DIRECTORY:** `/home/agnigate/Desktop/NMS` for local diagnostic shell
- **HOST PING:** FAIL / NOT VALID PRODUCTION EVIDENCE
- **HOST PING RETURN CODE:** `2` for `ping -4 -c 3 -W 2 192.168.100.2` in this shell
- **PING CAPABILITY:** `/usr/bin/ping` exists, mode `0755`, owned by `nobody:nogroup`, with `cap_net_raw=ep`
- **PYTHON RAW SOCKET:** FAIL in local shell
- **RAW SOCKET ERROR:** `PermissionError: [Errno 1] Operation not permitted`
- **CAP_NET_RAW AVAILABLE TO BACKEND:** UNKNOWN; no backend process. Not available to tested Python shell.
- **BACKEND RUN AS ROOT:** NO evidence; no backend process present. Local shell is UID 1000.

## Host ping evidence

Commands executed:

```text
ping -4 -c 3 -W 2 192.168.100.2
/usr/bin/ping -c 1 -W 1 192.168.100.2
```

Both returned code `2` with zero captured stdout/stderr in this managed environment. `/usr/bin/ping` has the expected `cap_net_raw=ep`, so this result is not sufficient to diagnose the actual Ubuntu NMS host. It is classified **NOT VALID PRODUCTION EVIDENCE**, not device unreachable.

## Python raw socket evidence

The tested interpreter was `/usr/bin/python3`, running as UID 1000. Minimal `AF_INET + SOCK_RAW + IPPROTO_ICMP` creation returned:

```text
PermissionError: [Errno 1] Operation not permitted
```

Classification: **PERMISSION_DENIED in the current sandbox**. Backend-specific capability remains unknown.

## Production fallback command

`hardik/backend/services/realtime_monitor.py` constructs this Linux fallback command:

```text
ping -c 1 -W 1 <target-ip>
```

For the selected target:

```text
/usr/bin/ping -c 1 -W 1 192.168.100.2
```

Observed in this shell:

- Return code: `2`
- stdout: empty
- stderr: empty
- Exact fallback result: cannot safely classify as production behavior

The code catches `OSError` and converts failures to `(False, None)`, so the production log’s repeated `timeout_or_error` is consistent with a failed fallback, but this run cannot prove whether the real host has a namespace, policy, command, or network issue.

## Fix decision

- **EXACT ROOT CAUSE:** Production host/service capability is **UNVERIFIABLE** from this environment. Local raw ICMP is denied, but the local shell is not the backend context.
- **FIX TYPE:** NONE
- **FIX APPLIED:** None
- **Reason:** No safe deployment-scoped capability change or fallback code change can be selected without the actual backend PID/service/container context and a same-user test.

Do not grant capabilities, chmod/chown `/usr/bin/ping`, or run the NMS as root based on this sandbox result.

## Post-fix production probe

| Probe | Result |
|---|---|
| Production probe 1 against 192.168.100.2 | PENDING — backend unavailable |
| Production probe 2 against 192.168.100.2 | PENDING — backend unavailable |
| Production probe 3 against 192.168.100.2 | PENDING — backend unavailable |
| RTT returned | PENDING |
| Worker → probe | PENDING for actual host; prior logs show failure in previous runtime |

## Explicit non-changes

- **SNMP changed:** NO
- **Scheduler changed:** NO
- **Health logic changed:** NO
- **DB status forced:** NO
- **Topology changed:** NO
- **Mock/static data added:** NO

## Acceptance boundary

- **SAFE FOR DB/PERSISTENCE VERIFICATION:** NO — this pass did not establish a valid production probe path.
- **Next required evidence:** run the commands as the actual backend service user/context on the Ubuntu NMS host, including service/container capability settings and the exact fallback command’s stdout/stderr/return code.

Stopped here as requested. No DB/API/UI work was performed.
