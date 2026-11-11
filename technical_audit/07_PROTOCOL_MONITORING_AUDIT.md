# Protocol and Monitoring Audit

| Protocol | Evidence | Behavior/status |
|---|---|---|
| ICMP | `monitoring_modules/icmp_monitor.py`, `discovery_modules/icmp_discovery.py` | Availability/discovery engine; scheduler restoration exists; unverified live execution |
| SNMP v2c/v3 | `backend/snmp/client.py`, `security.py`, collectors and scheduler | Polling, vendor/OID normalization, interfaces/environment/system modules; credentials/security code present; unverified |
| SSH | discovery and `services/remote_access/ssh_service.py` | Discovery and terminal access; host-key service exists; unverified |
| Telnet | `telnet_service.py` | Remote terminal adapter; security limitations inherent to protocol; unverified |
| WinRM/CIM | `windows_monitoring/winrm.py`, `cim.py`, `service.py` | Windows metrics, diagnostics, sensors/processes/trust; HTTPS/TLS trust configuration exists; unverified |
| Linux SSH/SNMP | `linux_monitoring/*` | Server detection, metrics, security and thresholds; unverified |
| Syslog UDP/TCP | `backend/syslog`, settings | Event-driven receiver, configurable ports 5514/6514, feature disabled by default |
| sFlow/IPFIX | `backend/flow/*`, settings | UDP receivers on 6343/4739, feature disabled by default |
| HTTP/HTTPS | discovery modules and API | HTTP discovery plus REST; deployment TLS termination is not verified |
| WebSocket | remote access route and frontend | Authenticated browser terminal transport; process-owned session adapter |

No evidence was found for an installed third-party Windows hardware agent such as LibreHardwareMonitor; native Windows sensor support is limited by available classes and returned values as documented in the Windows code.

