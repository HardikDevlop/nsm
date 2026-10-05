import { lazyRetry } from '../../components/lazyRetry'
import { withPermission } from '../../components/ProtectedLayout'

const AddSNMPDevice = lazyRetry(() => import('./pages/AddSNMPDevice'))
const SNMPCapabilities = lazyRetry(() => import('./pages/SNMPCapabilities'))
const SNMPCPUMonitoring = lazyRetry(() => import('./pages/SNMPCPUMonitoring'))
const SNMPDashboard = lazyRetry(() => import('./pages/SNMPDashboard'))
const SNMPDeviceDetails = lazyRetry(() => import('./pages/SNMPDeviceDetails'))
const SNMPDevices = lazyRetry(() => import('./pages/SNMPDevices'))
const SNMPEnvironmentMonitoring = lazyRetry(() => import('./pages/SNMPEnvironmentMonitoring'))
const SNMPGenericModulePage = lazyRetry(() => import('./pages/SNMPGenericModulePage'))
const SNMPInterfaceDetails = lazyRetry(() => import('./pages/SNMPInterfaceDetails'))
const SNMPInterfaceMonitoring = lazyRetry(() => import('./pages/SNMPInterfaceMonitoring'))
const SNMPLLDPMonitoring = lazyRetry(() => import('./pages/SNMPLLDPMonitoring'))
const SNMPMemoryMonitoring = lazyRetry(() => import('./pages/SNMPMemoryMonitoring'))
const SNMPMonitoring = lazyRetry(() => import('./pages/SNMPMonitoring'))
const SNMPMonitoringConfig = lazyRetry(() => import('./pages/SNMPMonitoringConfig'))
const SNMPOIDExplorer = lazyRetry(() => import('./pages/SNMPOIDExplorer'))
const SNMPPollingMonitoring = lazyRetry(() => import('./pages/SNMPPollingMonitoring'))
const SNMPRoutingMonitoring = lazyRetry(() => import('./pages/SNMPRoutingMonitoring'))
const SNMPStorageMonitoring = lazyRetry(() => import('./pages/SNMPStorageMonitoring'))
const SNMPVLANMonitoring = lazyRetry(() => import('./pages/SNMPVLANMonitoring'))

/** All SNMP URLs live under this feature route table. */
export const snmpRoutes = [
  { path: 'snmp-monitoring', Component: withPermission(SNMPMonitoring, 'devices:read') },
  { path: 'snmp/dashboard', Component: withPermission(SNMPDashboard, 'devices:read') },
  { path: 'snmp/dashboard/:deviceId', Component: withPermission(SNMPDashboard, 'devices:read') },
  { path: 'snmp/devices', Component: withPermission(SNMPDevices, 'devices:read') },
  { path: 'snmp/devices/add', Component: withPermission(AddSNMPDevice, 'devices:create') },
  { path: 'snmp/devices/:deviceId', Component: withPermission(SNMPDeviceDetails, 'devices:read') },
  { path: 'snmp/devices/:deviceId/monitoring', Component: withPermission(SNMPMonitoringConfig, 'devices:update') },
  { path: 'snmp/devices/:deviceId/cpu', Component: withPermission(SNMPCPUMonitoring, 'devices:read') },
  { path: 'snmp/devices/:deviceId/memory', Component: withPermission(SNMPMemoryMonitoring, 'devices:read') },
  { path: 'snmp/devices/:deviceId/interfaces', Component: withPermission(SNMPInterfaceMonitoring, 'devices:read') },
  { path: 'snmp/devices/:deviceId/interfaces/:interfaceId', Component: withPermission(SNMPInterfaceDetails, 'devices:read') },
  { path: 'snmp/devices/:deviceId/storage', Component: withPermission(SNMPStorageMonitoring, 'devices:read') },
  { path: 'snmp/devices/:deviceId/environment', Component: withPermission(SNMPEnvironmentMonitoring, 'devices:read') },
  { path: 'snmp/devices/:deviceId/vlan', Component: withPermission(SNMPVLANMonitoring, 'devices:read') },
  { path: 'snmp/devices/:deviceId/lldp', Component: withPermission(SNMPLLDPMonitoring, 'devices:read') },
  { path: 'snmp/devices/:deviceId/routing', Component: withPermission(SNMPRoutingMonitoring, 'devices:read') },
  { path: 'snmp/devices/:deviceId/topology', Component: withPermission(SNMPGenericModulePage, 'devices:read') },
  { path: 'snmp/devices/:deviceId/oids', Component: withPermission(SNMPOIDExplorer, 'devices:read') },
  { path: 'snmp/devices/:deviceId/polling', Component: withPermission(SNMPPollingMonitoring, 'devices:read') },
  { path: 'snmp/devices/:deviceId/capabilities', Component: withPermission(SNMPCapabilities, 'devices:read') },
  { path: 'snmp/devices/:deviceId/:moduleId', Component: withPermission(SNMPGenericModulePage, 'devices:read') },
  { path: 'snmp/capabilities', Component: withPermission(SNMPCapabilities, 'devices:read') },
  { path: 'snmp/capabilities/:deviceId', Component: withPermission(SNMPCapabilities, 'devices:read') },
]
