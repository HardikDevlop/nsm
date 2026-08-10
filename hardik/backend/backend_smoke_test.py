"""End-to-end smoke test for the FastAPI NMS Backend (all CRUD endpoints).

Usage (from c:\\Users\\Agnigate\\Desktop\\hardik):
    .\\.venv\\Scripts\\python.exe backend\\backend_smoke_test.py

The FastAPI server must be running on http://127.0.0.1:8000.
Start it with:
    python -m uvicorn backend.main:app --port 8000

The script logs in as the seeded admin user and then exercises every endpoint
in the Postman collection, printing a PASS/FAIL verdict per check.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable


BASE_URL = "http://127.0.0.1:8000/api/v1"
ADMIN_EMAIL = "admin@gmail.com"
ADMIN_PASSWORD = "admin123"


# ------------------------------- Harness ----------------------------------- #


class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    RESET = "\033[0m"


class Reporter:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.failures: list[str] = []
        self.started = time.time()

    def record(self, name: str, ok: bool, detail: str = "") -> None:
        tag = f"{Colors.GREEN}PASS{Colors.RESET}" if ok else f"{Colors.RED}FAIL{Colors.RESET}"
        line = f"[{tag}] {name}"
        if detail:
            line += f"  -- {detail}"
        print(line)
        if ok:
            self.passed += 1
        else:
            self.failed += 1
            self.failures.append(name)

    def summary(self) -> int:
        elapsed = round(time.time() - self.started, 2)
        total = self.passed + self.failed
        print("\n" + "=" * 70)
        print(f"Total: {total}   Passed: {self.passed}   Failed: {self.failed}   Time: {elapsed}s")
        if self.failures:
            print(f"{Colors.RED}Failed tests:{Colors.RESET}")
            for name in self.failures:
                print(f"  - {name}")
            return 1
        print(f"{Colors.GREEN}=== ALL CHECKS PASSED ==={Colors.RESET}")
        return 0


class ApiClient:
    """Thin urllib wrapper that maintains a bearer token header."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token: str = ""

    def set_token(self, token: str) -> None:
        self.token = token

    def request(
        self,
        method: str,
        path: str,
        body: Any = None,
        *,
        auth: bool = True,
    ) -> tuple[int, dict[str, Any]]:
        url = self.base_url + path
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8") or "{}"
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    payload = {"_raw": raw}
                return resp.status, payload
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace") or "{}"
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {"_raw": raw}
            return exc.code, payload


def check(
    reporter: Reporter,
    name: str,
    fn: Callable[[], tuple[int, dict]],
    *,
    expected: int = 200,
    expect_key: str | None = None,
) -> tuple[int, dict] | None:
    try:
        status, body = fn()
    except Exception as exc:  # pragma: no cover - harness only
        reporter.record(name, False, f"Exception: {exc}")
        return None
    if status != expected:
        snippet = json.dumps(body, ensure_ascii=False)[:200]
        reporter.record(name, False, f"status={status} expected={expected} body={snippet}")
        return None
    if expect_key is not None and (not isinstance(body, dict) or expect_key not in body):
        reporter.record(name, False, f"missing key '{expect_key}' in {list(body.keys()) if isinstance(body, dict) else type(body).__name__}")
        return None
    reporter.record(name, True, f"status={status}")
    return status, body


# ------------------------------ Test Cases --------------------------------- #


def run_tests() -> int:
    client = ApiClient(BASE_URL)
    reporter = Reporter()
    run_tag = str(int(time.time()))[-6:]

    # --- Health ---
    check(reporter, "GET /health", lambda: client.request("GET", "/health", auth=False))

    # --- Auth ---
    def login():
        status, body = client.request("POST", "/auth/login", {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, auth=False)
        if status == 200 and "access_token" in body:
            client.set_token(body["access_token"])
        return status, body

    resp = check(reporter, "POST /auth/login", login, expect_key="access_token")
    if resp is None:
        print(f"{Colors.RED}Login failed, cannot continue without token{Colors.RESET}")
        return reporter.summary()

    check(reporter, "GET /auth/me", lambda: client.request("GET", "/auth/me"), expect_key="email")

    # --- Dashboard ---
    check(reporter, "GET /dashboard/summary", lambda: client.request("GET", "/dashboard/summary"))

    # --- CRUD modules ---
    crud_modules = [
        ("organizations", {"name": f"Smoke Org {run_tag}", "description": "smoke"}, {"description": "updated"}),
        ("sites", {"organization_id": None, "name": f"Smoke Site {run_tag}"}, {"city": "Delhi"}),
        ("vendors", {"vendor_name": f"SmokeVendor {run_tag}"}, {"vendor_name": f"SmokeVendorUpdated {run_tag}"}),
        ("device-types", {"name": f"SmokeType {run_tag}", "description": "smoke"}, {"description": "updated"}),
    ]
    created_ids: dict[str, int] = {}
    for slug, create_body, update_body in crud_modules:
        module_label = slug.replace("-", " ").title()
        if slug == "sites":
            # ensure an organization exists first
            if "organizations" in created_ids:
                create_body = dict(create_body, organization_id=created_ids["organizations"])
            else:
                # create one on the fly
                s, b = client.request("POST", "/organizations", {"name": "Auto Org"})
                if s in (200, 201) and isinstance(b, dict) and b.get("id"):
                    created_ids["organizations"] = b["id"]
                    create_body = dict(create_body, organization_id=b["id"])

        resp = check(reporter, f"POST /{slug} ({module_label})", lambda b=create_body, s=slug: client.request("POST", f"/{s}", b), expected=201)
        if resp and isinstance(resp[1], dict) and resp[1].get("id"):
            created_ids[slug] = resp[1]["id"]
        item_id = created_ids.get(slug, 1)
        check(reporter, f"GET /{slug} (list)", lambda s=slug: client.request("GET", f"/{s}"))
        check(reporter, f"GET /{slug}/{{id}}", lambda s=slug, i=item_id: client.request("GET", f"/{s}/{i}"))
        check(reporter, f"PATCH /{slug}/{{id}}", lambda s=slug, i=item_id, b=update_body: client.request("PATCH", f"/{s}/{i}", b))

    # --- Devices ---
    device_payload = {
        "site_id": created_ids.get("sites", 1),
        "vendor_id": created_ids.get("vendors", 1),
        "device_type_id": created_ids.get("device-types", 1),
        "hostname": f"smoke-device-{run_tag}",
        "ip_address": f"192.168.{int(run_tag) % 256}.{int(run_tag[-3:]) % 256 or 1}",
        "model": "SMOKE-100",
    }
    resp = check(reporter, "POST /devices", lambda: client.request("POST", "/devices", device_payload), expected=201)
    device_id = resp[1]["id"] if resp and isinstance(resp[1], dict) else 1
    created_ids["devices"] = device_id
    check(reporter, "GET /devices (list)", lambda: client.request("GET", "/devices"))
    check(reporter, "GET /devices/{id}", lambda: client.request("GET", f"/devices/{device_id}"))
    check(reporter, "PATCH /devices/{id}", lambda: client.request("PATCH", f"/devices/{device_id}", {"hostname": "smoke-updated"}))
    check(reporter, "POST /devices/{id}/monitoring/true", lambda: client.request("POST", f"/devices/{device_id}/monitoring/true"))
    check(reporter, "GET /devices/{id}/status-history", lambda: client.request("GET", f"/devices/{device_id}/status-history"))

    # --- Device Credentials ---
    cred_payload = {"device_id": device_id, "protocol": "ssh", "username": "admin", "password": "secret", "port": 22}
    resp = check(reporter, "POST /device-credentials", lambda: client.request("POST", "/device-credentials", cred_payload), expected=201)
    cred_id = resp[1]["id"] if resp and isinstance(resp[1], dict) else 1
    check(reporter, "GET /device-credentials (list)", lambda: client.request("GET", "/device-credentials"))
    check(reporter, "GET /device-credentials/{id}", lambda: client.request("GET", f"/device-credentials/{cred_id}"))
    check(reporter, "PATCH /device-credentials/{id}", lambda: client.request("PATCH", f"/device-credentials/{cred_id}", {"port": 2222}))

    # --- Interfaces ---
    if_payload = {
        "device_id": device_id,
        "interface_name": "GigabitEthernet0/1",
        "status": "up",
        "speed": "1Gbps",
        "traffic_in": 0,
        "traffic_out": 0,
        "packet_errors": 0,
    }
    resp = check(reporter, "POST /interfaces", lambda: client.request("POST", "/interfaces", if_payload), expected=201)
    iface_id = resp[1]["id"] if resp and isinstance(resp[1], dict) else 1
    check(reporter, "GET /interfaces (list)", lambda: client.request("GET", "/interfaces"))
    check(reporter, "GET /interfaces/{id}", lambda: client.request("GET", f"/interfaces/{iface_id}"))
    check(reporter, "PATCH /interfaces/{id}", lambda: client.request("PATCH", f"/interfaces/{iface_id}", {"status": "down"}))

    # --- Monitoring Jobs ---
    job_payload = {"device_id": device_id, "monitor_type": "icmp", "interval": 60, "status": "active"}
    resp = check(reporter, "POST /monitoring-jobs", lambda: client.request("POST", "/monitoring-jobs", job_payload), expected=201)
    job_id = resp[1]["id"] if resp and isinstance(resp[1], dict) else 1
    check(reporter, "GET /monitoring-jobs (list)", lambda: client.request("GET", "/monitoring-jobs"))
    check(reporter, "GET /monitoring-jobs/{id}", lambda: client.request("GET", f"/monitoring-jobs/{job_id}"))
    check(reporter, "PATCH /monitoring-jobs/{id}", lambda: client.request("PATCH", f"/monitoring-jobs/{job_id}", {"interval": 30}))

    # --- Device Metrics ---
    metric_payload = {"device_id": device_id, "metric_name": "cpu_percent", "metric_value": 42.0, "unit": "%"}
    resp = check(reporter, "POST /device-metrics", lambda: client.request("POST", "/device-metrics", metric_payload), expected=201)
    metric_id = resp[1]["id"] if resp and isinstance(resp[1], dict) else 1
    check(reporter, "GET /device-metrics (list)", lambda: client.request("GET", "/device-metrics"))
    check(reporter, "GET /device-metrics/{id}", lambda: client.request("GET", f"/device-metrics/{metric_id}"))
    check(reporter, "PATCH /device-metrics/{id}", lambda: client.request("PATCH", f"/device-metrics/{metric_id}", {"metric_value": 55.0}))

    # --- Thresholds ---
    threshold_payload = {"device_id": device_id, "metric_name": "cpu_percent", "warning_value": 80, "critical_value": 95}
    resp = check(reporter, "POST /thresholds", lambda: client.request("POST", "/thresholds", threshold_payload), expected=201)
    thr_id = resp[1]["id"] if resp and isinstance(resp[1], dict) else 1
    check(reporter, "GET /thresholds (list)", lambda: client.request("GET", "/thresholds"))
    check(reporter, "GET /thresholds/{id}", lambda: client.request("GET", f"/thresholds/{thr_id}"))
    check(reporter, "PATCH /thresholds/{id}", lambda: client.request("PATCH", f"/thresholds/{thr_id}", {"critical_value": 90}))

    # --- Alerts + acknowledge + resolve ---
    alert_payload = {"device_id": device_id, "severity": "critical", "title": "Smoke Alert", "description": "test"}
    resp = check(reporter, "POST /alerts", lambda: client.request("POST", "/alerts", alert_payload), expected=201)
    alert_id = resp[1]["id"] if resp and isinstance(resp[1], dict) else 1
    check(reporter, "GET /alerts (list)", lambda: client.request("GET", "/alerts"))
    check(reporter, "GET /alerts/{id}", lambda: client.request("GET", f"/alerts/{alert_id}"))
    check(reporter, "PATCH /alerts/{id}", lambda: client.request("PATCH", f"/alerts/{alert_id}", {"severity": "warning"}))
    check(reporter, "POST /alerts/{id}/acknowledge", lambda: client.request("POST", f"/alerts/{alert_id}/acknowledge"))
    check(reporter, "POST /alerts/{id}/resolve", lambda: client.request("POST", f"/alerts/{alert_id}/resolve"))

    # --- Events ---
    event_payload = {"device_id": device_id, "event_type": "status_change", "severity": "info", "message": "smoke"}
    resp = check(reporter, "POST /events", lambda: client.request("POST", "/events", event_payload), expected=201)
    event_id = resp[1]["id"] if resp and isinstance(resp[1], dict) else 1
    check(reporter, "GET /events (list)", lambda: client.request("GET", "/events"))
    check(reporter, "GET /events/{id}", lambda: client.request("GET", f"/events/{event_id}"))
    check(reporter, "PATCH /events/{id}", lambda: client.request("PATCH", f"/events/{event_id}", {"severity": "warning"}))

    # --- Notifications ---
    notif_payload = {"alert_id": alert_id, "channel": "email", "sent_to": "smoke@example.com", "status": "pending"}
    resp = check(reporter, "POST /notifications", lambda: client.request("POST", "/notifications", notif_payload), expected=201)
    notif_id = resp[1]["id"] if resp and isinstance(resp[1], dict) else 1
    check(reporter, "GET /notifications (list)", lambda: client.request("GET", "/notifications"))
    check(reporter, "GET /notifications/{id}", lambda: client.request("GET", f"/notifications/{notif_id}"))
    check(reporter, "PATCH /notifications/{id}", lambda: client.request("PATCH", f"/notifications/{notif_id}", {"status": "delivered"}))

    # --- Reports ---
    report_payload = {"report_name": "Smoke Report", "report_type": "uptime", "file_path": "/tmp/smoke.pdf"}
    resp = check(reporter, "POST /reports", lambda: client.request("POST", "/reports", report_payload), expected=201)
    report_id = resp[1]["id"] if resp and isinstance(resp[1], dict) else 1
    check(reporter, "GET /reports (list)", lambda: client.request("GET", "/reports"))
    check(reporter, "GET /reports/{id}", lambda: client.request("GET", f"/reports/{report_id}"))
    check(reporter, "PATCH /reports/{id}", lambda: client.request("PATCH", f"/reports/{report_id}", {"report_name": "Updated"}))

    # --- Audit Logs (read-only) ---
    check(reporter, "GET /audit-logs (list)", lambda: client.request("GET", "/audit-logs"))

    # --- Roles + permissions ---
    check(reporter, "GET /roles (list)", lambda: client.request("GET", "/roles"))
    resp = check(reporter, "POST /roles", lambda: client.request("POST", "/roles", {"role_name": "SmokeRole"}), expected=201)
    role_id = resp[1]["id"] if resp and isinstance(resp[1], dict) else 1
    check(reporter, "GET /roles/{id}", lambda: client.request("GET", f"/roles/{role_id}"))
    check(reporter, "PATCH /roles/{id}", lambda: client.request("PATCH", f"/roles/{role_id}", {"description": "smoke"}))
    check(reporter, "GET /roles/{id}/permissions", lambda: client.request("GET", f"/roles/{role_id}/permissions"))
    # Create 3 known-good permissions first, then replace role perms with those ids
    _created_perm_ids_for_cleanup: list[int] = []
    temp_perm_ids: list[int] = []
    for idx in range(3):
        s, b = client.request(
            "POST",
            "/permissions",
            {"code": f"smoke:temp{idx}:{run_tag}", "name": f"Temp {idx}", "module": "smoke", "action": f"temp{idx}"},
        )
        if s == 201 and isinstance(b, dict) and b.get("id"):
            temp_perm_ids.append(b["id"])
    check(
        reporter,
        "PUT /roles/{id}/permissions (replace)",
        lambda: client.request("PUT", f"/roles/{role_id}/permissions", {"permission_ids": temp_perm_ids}),
    )
    perm_to_add = temp_perm_ids[0] if temp_perm_ids else 1
    check(reporter, "POST /roles/{id}/permissions/{perm_id}", lambda: client.request("POST", f"/roles/{role_id}/permissions/{perm_to_add}"))
    check(reporter, "DELETE /roles/{id}/permissions/{perm_id}", lambda: client.request("DELETE", f"/roles/{role_id}/permissions/{perm_to_add}"))
    _created_perm_ids_for_cleanup = temp_perm_ids

    # --- Permissions ---
    check(reporter, "GET /permissions (list)", lambda: client.request("GET", "/permissions"))
    resp = check(
        reporter,
        "POST /permissions",
        lambda: client.request("POST", "/permissions", {"code": f"smoke:execute:{run_tag}", "name": f"Smoke Execute {run_tag}", "module": "smoke", "action": "execute"}),
        expected=201,
    )
    perm_id = resp[1]["id"] if resp and isinstance(resp[1], dict) else 1
    check(reporter, "GET /permissions/{id}", lambda: client.request("GET", f"/permissions/{perm_id}"))
    check(reporter, "PATCH /permissions/{id}", lambda: client.request("PATCH", f"/permissions/{perm_id}", {"description": "smoke"}))

    # --- Users ---
    user_payload = {"name": f"Smoke User {run_tag}", "email": f"smoke{run_tag}@example.com", "password": "smoke123", "role_id": role_id}
    resp = check(reporter, "POST /users", lambda: client.request("POST", "/users", user_payload), expected=201)
    user_id = resp[1]["id"] if resp and isinstance(resp[1], dict) else 2
    check(reporter, "GET /users (list)", lambda: client.request("GET", "/users"))
    check(reporter, "GET /users/{id}", lambda: client.request("GET", f"/users/{user_id}"))
    check(reporter, "PATCH /users/{id}", lambda: client.request("PATCH", f"/users/{user_id}", {"full_name": "Smoke Updated"}))
    check(reporter, "POST /users/{id}/role", lambda: client.request("POST", f"/users/{user_id}/role", {"role_id": role_id}))

    # --- Discovery & Monitoring services ---
    check(
        reporter,
        "POST /discovery/run",
        lambda: client.request(
            "POST",
            "/discovery/run",
            {"network_range": "127.0.0.1/32", "ports": [80], "timeout_ms": 500, "scan_icmp": True, "scan_snmp": False, "max_hosts": 1},
        ),
        expected=201,
    )
    check(
        reporter,
        "POST /monitoring/run",
        lambda: client.request("POST", "/monitoring/run", {"ip_addresses": ["127.0.0.1"], "timeout_ms": 500}),
    )

    # --- Cleanup (deletes in reverse dependency order) ---
    for path in [
        f"/notifications/{notif_id}",
        f"/reports/{report_id}",
        f"/events/{event_id}",
        f"/alerts/{alert_id}",
        f"/thresholds/{thr_id}",
        f"/device-metrics/{metric_id}",
        f"/monitoring-jobs/{job_id}",
        f"/interfaces/{iface_id}",
        f"/device-credentials/{cred_id}",
        f"/devices/{device_id}",
        f"/users/{user_id}",
        f"/permissions/{perm_id}",
        f"/roles/{role_id}",
    ]:
        check(reporter, f"DELETE {path}", lambda p=path: client.request("DELETE", p))

    # Cleanup temporary permissions created for role-permission test
    for pid in _created_perm_ids_for_cleanup:
        check(reporter, f"DELETE /permissions/{pid} (temp)", lambda p=pid: client.request("DELETE", f"/permissions/{p}"))

    for slug in ("device-types", "vendors", "sites", "organizations"):
        item_id = created_ids.get(slug, 1)
        check(reporter, f"DELETE /{slug}/{{id}}", lambda s=slug, i=item_id: client.request("DELETE", f"/{s}/{i}"))

    return reporter.summary()


if __name__ == "__main__":
    sys.exit(run_tests())
