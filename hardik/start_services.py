"""Launch the unified NMS backend (single FastAPI service on port 8000).

The legacy Flask Discovery Service (icmp_discovery/app.py, port 5000) is
deprecated — all its endpoints now live inside the FastAPI backend.

Usage:
    cd C:\\Users\\Agnigate\\Desktop\\hardik
    .\\.venv\\Scripts\\python.exe start_services.py

Starts:
    - FastAPI NMS Backend  -> http://127.0.0.1:8000
        CRUD + JWT Auth + RBAC
        Discovery / Monitoring / Analytics modules
        Legacy /api/inventory + /api/discovery/* routes

Press Ctrl+C to stop.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time


ROOT = os.path.dirname(os.path.abspath(__file__))
PYTHON = sys.executable


def start() -> int:
    print("=" * 70)
    print("AgniGate NMS - unified backend")
    print("=" * 70)

    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")

    backend = subprocess.Popen(
        [PYTHON, "-m", "uvicorn", "backend.main:app",
         "--host", "127.0.0.1", "--port", "8000", "--reload"],
        cwd=ROOT,
        env=env,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )
    print(f"  FastAPI Backend      PID={backend.pid}  http://127.0.0.1:8000")
    print("-" * 70)
    print("Press Ctrl+C to stop.")
    print("-" * 70)

    def shutdown(signum=None, frame=None):
        print("\nStopping backend...")
        if backend.poll() is None:
            try:
                backend.terminate()
            except Exception:
                pass
        try:
            backend.wait(timeout=5)
        except subprocess.TimeoutExpired:
            backend.kill()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        while True:
            if backend.poll() is not None:
                print(f"Backend exited with code {backend.returncode}")
                shutdown()
            time.sleep(2)
    except KeyboardInterrupt:
        shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(start())
