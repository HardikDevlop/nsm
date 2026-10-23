# Windows sensor provider integration

Phase 2B defines the provider contract only. Native WMI/CIM remains the
first provider and continues to use the existing authenticated WinRM HTTPS
session. It is read-only and does not execute arbitrary PowerShell.

LibreHardwareMonitor cannot be collected from a normal Windows host merely by
querying the existing Win32 classes. Its sensor model requires the
LibreHardwareMonitor application/service (or an equivalent Windows-side
provider) to be installed and granted the hardware-access permissions it
needs. Phase 2B deliberately does not install or contact that provider.

The next implementation chunk should add a Windows-side, least-privilege
provider service with a fixed read-only contract. The NMS backend should
access it through the existing device credential and verified WinRM HTTPS
transport, using an allow-listed CIM/WMI class or a narrowly defined provider
endpoint. It must validate the provider identity, preserve TLS certificate
validation and RBAC, apply request/response size and timeout limits, and map
provider absence, access denial and collection errors to the existing sensor
statuses. No arbitrary PowerShell or unauthenticated HTTP listener should be
introduced.

Expected future sensor types include CPU package/core temperature, CPU/system
fan RPM, motherboard temperature, GPU temperature/utilization and
SSD/NVMe temperature. A device may legitimately return no readings; the UI
must show `unsupported`, `unavailable`, `permission_denied` or
`provider_not_installed` rather than fabricate zero values.
