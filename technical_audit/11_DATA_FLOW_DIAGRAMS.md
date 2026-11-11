# End-to-End Data Flows

The diagrams describe source-supported paths and use **UNVERIFIED** where no runtime execution was permitted.

## Overall

```mermaid
flowchart LR
 UI[React/Vite SPA] --> API[FastAPI routers]
 API --> S[Services/adapters]
 S --> D[(PostgreSQL)]
 S --> A[Alerts/reports/events]
 A --> UI
 API -. terminal .-> WS[Authenticated WebSocket]
 WS --> RA[SSH/Telnet session manager]
```

## Monitoring

```mermaid
flowchart LR
 SCH[SNMP/Linux/ICMP scheduler] --> P[Protocol adapter]
 P --> DEV[Network or OS device]
 DEV --> N[Normalize metrics]
 N --> DB[(Snapshots/history)]
 DB --> TH[Threshold evaluation]
 TH --> AL[Alert/notification]
 DB --> DASH[Dashboard/report APIs]
```

## Authentication/RBAC

```mermaid
sequenceDiagram
 participant U as User
 participant F as Frontend
 participant A as Auth API/dependency
 participant DB as PostgreSQL
 U->>F: credentials
 F->>A: login
 A->>DB: verify bcrypt user/session
 A-->>F: JWT
 F->>A: bearer request
 A->>A: decode token, permission and site scope
 A-->>F: response or 401/403
```

Device onboarding/discovery, WinRM monitoring, alert recovery, report generation, and collector ingestion are represented by corresponding service/router/model code, but each remains runtime **UNVERIFIED**. A separate remote-collector architecture is not supported by verified repository evidence.

