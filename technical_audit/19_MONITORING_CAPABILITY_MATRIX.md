# Monitoring Capability Matrix

| Protocol/capability | Ports/defaults | Auth/security | Poll/event behavior | Timeout/retry evidence | Metrics/evidence | Status |
|---|---|---|---|---|---|---|
| ICMP | OS ping; timeout from `config.py` | network reachability | scheduled polling/discovery | `PING_TIMEOUT`, `PING_COUNT`, worker pool | reachability/latency via ICMP monitor | S/U |
| SNMP | 161 device; trap receiver constant in legacy config | v2c/v3 security/client modules | scheduler polling, collectors, raw cache | settings: request timeout 3s, retries 1, operation timeout 120s | CPU, memory, storage, interfaces, environment, routing, VLAN, LLDP/CDP, ARP, inventory, health | S/U |
| SSH | 22 | credentials and host-key trust for remote access | discovery/banner and interactive session | discovery socket timeout from config; service-specific runtime unverified | banner/platform hints; terminal access | S/U |
| Telnet | conventional 23 | username/password; plaintext protocol | interactive session | service implementation; exact retry/timeout unverified | terminal access | S/U |
| WinRM/HTTPS/CIM | 5986 HTTPS; 5985 HTTP appears in discovery | WinRM credentials, CA trust/TLS diagnostics | on-demand/scheduled Windows collection | service/resource-budget settings; exact end-to-end retry unverified | system, CPU, memory, disks, processes, events, TCP, hardware sensors, trust diagnostics | S/U |
| WMI discovery | 135/445/5985/5986 candidate ports | WMI command path | discovery probe | `WMI_TIMEOUT_SECONDS` | OS/Windows reachability evidence | S/U |
| Linux | SSH/SNMP paths | credentials/protocol validation | Linux scheduler restore and collection | implementation exists; exact matrix unverified | system metrics, security/events, thresholds | S/U |
| Syslog | settings default UDP 5514/TCP 6514 | transport/configuration; no claim of TLS from source | event-driven receiver | receiver socket behavior; retention default 0 | facility/severity/hostname/app/message and correlations | S/U; disabled by default |
| sFlow/IPFIX | 6343/4739 | bind/configuration | UDP ingestion | parser/service behavior | flow records and sFlow counters | S/U; disabled by default |
| HTTP/HTTPS discovery | candidate HTTP ports from `config.py`/open-port evidence | HTTP/HTTPS scheme selection | discovery request | `HTTP_TIMEOUT_SECONDS` | banner/status/header evidence | S/U |

The earlier audit should not describe ports as active listeners: `flow_enabled` and `syslog_enabled` default false, and runtime configuration was not inspected. Authentication details are source-supported, not credential-success evidence.

