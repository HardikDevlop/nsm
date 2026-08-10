"""Unified smoke test for the consolidated FastAPI NMS backend.

Everything now runs on a single port (8000):
    - CRUD + RBAC + Auth (previously FastAPI port 8000)
    - Discovery / Monitoring / Analytics modules (previously Flask port 5000)
    - Legacy endpoints (/api/inventory, /api/discovery/*) for React frontend

Run:
    cd C:\\Users\\Agnigate\\Desktop\\hardik
    .\\.venv\\Scripts\\python.exe backend\\unified_smoke_test.py
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

BASE = "0.0.0.0"
PASS = 0
FAIL = 0
RUN_TAG = str(int(time.time()))[-6:]
_counters = {"pass": 0, "fail": 0}


def check(name: str, method: str, url: str, expected: int = 200, body: dict | None = None) -> int:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            code = resp.status
            text = resp.read().decode()
    except urllib.error.HTTPError as exc:
        code = exc.code
        text = exc.read().decode() if exc.fp else ""

    ok = code == expected
    mark = "PASS" if ok else "FAIL"
    snippet = (text[:80] + ("..." if len(text) > 80 else "")).replace("\n", " ")
    print(f"  [{mark}] {method:5} {name:55} expect={expected} got={code}  ::  {snippet}")
    if ok:
        _counters["pass"] += 1
    else:
        _counters["fail"] += 1
    return code


def main() -> None:
    print("=" * 80)
    print(f"Unified NMS Smoke Test — {BASE}  (tag={RUN_TAG})")
    print("=" * 80)

    # ---------- Health ----------
    check("GET /api/v1/health", "GET", f"{BASE}/api/v1/health")
    check("GET /api/v1/discovery/modules", "GET", f"{BASE}/api/v1/discovery/modules")
    
    # ---------- Legacy (backward-compat) ----------
    check("GET /api/inventory (legacy)", "GET", f"{BASE}/api/inventory")
    check("GET /api/discovery/modules (legacy)", "GET", f"{BASE}/api/discovery/modules")
    check("GET /api/discovery/summary (legacy)", "GET", f"{BASE}/api/discovery/summary")
    
    # ---------- Discovery modules (no auth) ----------
    check("POST /api/v1/discovery/icmp (empty -> 400)", "POST",
          f"{BASE}/api/v1/discovery/icmp", expected=400, body={"ips": []})
    check("POST /api/v1/discovery/icmp (valid)", "POST",
          f"{BASE}/api/v1/discovery/icmp", body={"ips": ["127.0.0.1"], "timeout_ms": 500})
    check("POST /api/v1/discovery/dns (valid)", "POST",
          f"{BASE}/api/v1/discovery/dns", body={"ips": ["127.0.0.1"]})
    check("POST /api/v1/discovery/arp (valid)", "POST",
          f"{BASE}/api/v1/discovery/arp", body={"ips": ["127.0.0.1"]})
    check("POST /api/v1/discovery/profile (empty -> 400)", "POST",
          f"{BASE}/api/v1/discovery/profile", expected=400, body={"signals": {}})
    check("POST /api/v1/discovery/profile (valid)", "POST",
          f"{BASE}/api/v1/discovery/profile",
          body={"signals": {"open_ports": {22: "ssh", 80: "http"}, "snmp_name": "test"}})

    # ---------- Monitoring modules (no auth) ----------
    check("POST /api/v1/monitoring/icmp (valid)", "POST",
          f"{BASE}/api/v1/monitoring/icmp", body={"ips": ["127.0.0.1"], "timeout_ms": 500})
    check("POST /api/v1/monitoring/syslog/parse (valid)", "POST",
          f"{BASE}/api/v1/monitoring/syslog/parse",
          body={"message": "<134>Jul 28 10:00:00 host app: test msg", "source_ip": "10.0.0.1"})

    # ---------- Analytics (no auth) ----------
    check("POST /api/v1/analytics/events/normalize", "POST",
          f"{BASE}/api/v1/analytics/events/normalize",
          body={"events": [{"ts": 1, "type": "TEST", "src": "x"}]})
    check("POST /api/v1/analytics/topology", "POST",
          f"{BASE}/api/v1/analytics/topology", body={"devices": []})
    check("GET /api/v1/analytics/alerts/thresholds", "POST",
          f"{BASE}/api/v1/analytics/alerts/thresholds", body={})

    # ---------- Auth (admin) ----------
    code, token = 0, ""
    try:
        req = urllib.request.Request(
            f"{BASE}/api/v1/auth/login",
            data=json.dumps({"email": "admin@gmail.com", "password": "admin123"}).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            code = resp.status
            payload = json.loads(resp.read())
            token = payload.get("access_token", "")
    except urllib.error.HTTPError as exc:
        code = exc.code
    ok = code == 200 and bool(token)
    print(f"  [{'PASS' if ok else 'FAIL'}] POST   /api/v1/auth/login                                       expect=200 got={code}")
    if ok:
        _counters["pass"] += 1
    else:
        _counters["fail"] += 1

    if not token:
        print("\n  (!) No token — skipping protected endpoints.")
    else:
        auth = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        def auth_check(name: str, method: str, url: str, expected: int = 200, body: dict | None = None) -> None:
            data = json.dumps(body).encode() if body is not None else None
            req = urllib.request.Request(url, data=data, method=method, headers=auth)
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    sc = resp.status
                    text = resp.read().decode()
            except urllib.error.HTTPError as exc:
                sc = exc.code
                text = exc.read().decode() if exc.fp else ""
            ok_ = sc == expected
            snippet = (text[:80] + ("..." if len(text) > 80 else "")).replace("\n", " ")
            print(f"  [{'PASS' if ok_ else 'FAIL'}] {method:5} {name:55} expect={expected} got={sc}  ::  {snippet}")
            if ok_:
                _counters["pass"] += 1
            else:
                _counters["fail"] += 1

        auth_check("GET /api/v1/auth/me", "GET", f"{BASE}/api/v1/auth/me")
        auth_check("GET /api/v1/dashboard/summary", "GET", f"{BASE}/api/v1/dashboard/summary")
        auth_check("GET /api/v1/organizations", "GET", f"{BASE}/api/v1/organizations")
        auth_check("GET /api/v1/sites", "GET", f"{BASE}/api/v1/sites")
        auth_check("GET /api/v1/vendors", "GET", f"{BASE}/api/v1/vendors")
        auth_check("GET /api/v1/device-types", "GET", f"{BASE}/api/v1/device-types")
        auth_check("GET /api/v1/devices", "GET", f"{BASE}/api/v1/devices")
        auth_check("GET /api/v1/roles", "GET", f"{BASE}/api/v1/roles")
        auth_check("GET /api/v1/users", "GET", f"{BASE}/api/v1/users")
        auth_check("GET /api/v1/permissions", "GET", f"{BASE}/api/v1/permissions")
        auth_check("GET /api/v1/audit-logs", "GET", f"{BASE}/api/v1/audit-logs")

        # Protected discovery/monitoring endpoints (admin has discovery:execute permission, so 201 OK)
        auth_check("POST /api/v1/discovery/run (admin allowed)", "POST",
                   f"{BASE}/api/v1/discovery/run", expected=201,
                   body={"network_range": "127.0.0.1/32", "max_hosts": 1, "timeout_ms": 500})

    print("=" * 80)
    print(f"RESULT: {_counters['pass']} pass / {_counters['fail']} fail / {_counters['pass'] + _counters['fail']} total")
    print("=" * 80)
    raise SystemExit(0 if _counters['fail'] == 0 else 1)


if __name__ == "__main__":
    main()
