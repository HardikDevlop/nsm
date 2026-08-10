---
kind: build_system
name: Build System — No Centralized Build Pipeline
category: build_system
scope:
    - '**'
source_files:
    - icmp_discovery/requirements.txt
    - backend/requirements.txt
    - frontend/package.json
    - icmp_discovery/README.md
---

This repository does not implement a centralized build system. There are no Makefiles, Dockerfiles, CI/CD pipelines (GitHub Actions, GitLab CI, Jenkins), or shell-based build scripts at the repository root or within any subdirectory. Each service manages its own dependencies and development workflow independently:

- **ICMP Discovery Engine** (`icmp_discovery/`): A Python Flask application with a minimal `requirements.txt` listing only `pytest>=8.0.0` and `Flask>=3.0.0`. The README documents running via `.venv\Scripts\python.exe main.py` and testing via `python -m pytest`, indicating a local virtual environment is used for isolation.
- **Backend API** (`backend/`): A FastAPI application with a `requirements.txt` declaring runtime dependencies (FastAPI, Uvicorn, SQLAlchemy, Pydantic, etc.). Development appears to be done directly with `pip install -r requirements.txt` in a local `.venv`.
- **Frontend Dashboard** (`frontend/`): A React + Vite SPA managed through `package.json` with standard npm scripts (`dev`, `build`, `lint`, `preview`). Linting uses Oxlint via `@oxlintrc.json`.

There is no cross-service orchestration script, no containerization configuration, no version pinning strategy beyond minimum versions in `requirements.txt`, and no automated test or lint gates. The project relies on developers to manually activate virtual environments and run each service's entry point or npm script individually.