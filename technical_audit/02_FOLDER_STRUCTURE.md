# Folder Structure Audit

Generated from repository paths while excluding `.git`, virtual environments, caches, generated binaries and vendor content.

```text
NMS/
├── hardik/
│   ├── backend/
│   │   ├── api/                 # REST routers: core, discovery, SNMP, ITSM and integrations
│   │   ├── auth/                # JWT/password and authority helpers
│   │   ├── config/              # pydantic settings
│   │   ├── database/            # SQLAlchemy session and idempotent migrations
│   │   ├── models/              # ORM models for core and feature domains
│   │   ├── services/            # monitoring, polling, reports, alerts, discovery, remote access
│   │   ├── snmp/                # clients, schedulers, collectors, normalization and identity
│   │   ├── windows_monitoring/  # WinRM/CIM, snapshots, processes, trust and diagnostics
│   │   ├── linux_monitoring/    # Linux server models, metrics, scheduler and APIs
│   │   ├── flow/                # sFlow/IPFIX receivers, parsers and persistence
│   │   ├── syslog/              # syslog ingestion service
│   │   ├── schemas/             # Pydantic request/response schemas
│   │   └── postman/             # API collection
│   ├── discovery_modules/       # protocol-specific discovery engines
│   ├── analytics_modules/       # topology, event and alert engines
│   ├── docs/                    # feature and operational documentation
│   └── tests/                   # backend test suites and focused regressions
├── figma design/
│   ├── src/pages/               # 53 routed UI pages
│   ├── src/components/          # layout, auth, permissions, Windows and shared UI
│   ├── src/features/snmp/       # SNMP feature routes, hooks, modules and components
│   ├── src/lib/api.ts           # frontend API client/types
│   └── tests/                   # 61 Node frontend regression tests
├── data/logs/                   # runtime log location present in tree
└── db_backups/                  # database dump artifacts
```

Notable nonstandard files include root service scripts, `hardik/continuous_monitoring.py`, legacy/top-level monitoring scripts, generated report output, and user worktree changes. They were preserved.

