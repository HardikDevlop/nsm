import { lazy } from 'react'
import { withPermission } from '../../components/ProtectedLayout'

const AddSNMPDevice = lazy(() => import('./pages/AddSNMPDevice'))
const SNMPCapabilities = lazy(() => import('./pages/SNMPCapabilities'))
const SNMPCPUMonitoring = lazy(() => import('./pages/SNMPCPUMonitoring'))
const SNMPDashboard = lazy(() => import('./pages/SNMPDashboard'))
const SNMPDeviceDetails = lazy(() => import('./pages/SNMPDeviceDetails'))
const SNMPDevices = lazy(() => import('./pages/SNMPDevices'))
const SNMPEnvironmentMonitoring = lazy(() => import('./pages/SNMPEnvironmentMonitoring'))
const SNMPGenericModulePage = lazy(() => import('./pages/SNMPGenericModulePage'))
const SNMPInterfaceDetails = lazy(() => import('./pages/SNMPInterfaceDetails'))
const SNMPInterfaceMonitoring = lazy(() => import('./pages/SNMPInterfaceMonitoring'))
const SNMPLLDPMonitoring = lazy(() => import('./pages/SNMPLLDPMonitoring'))
const SNMPMemoryMonitoring = lazy(() => import('./pages/SNMPMemoryMonitoring'))
const SNMPMonitoring = lazy(() => import('./pages/SNMPMonitoring'))
const SNMPMonitoringConfig = lazy(() => import('./pages/SNMPMonitoringConfig'))
const SNMPOIDExplorer = lazy(() => import('./pages/SNMPOIDExplorer'))
const SNMPPollingMonitoring = lazy(() => import('./pages/SNMPPollingMonitoring'))
const SNMPRoutingMonitoring = lazy(() => import('./pages/SNMPRoutingMonitoring'))
const SNMPStorageMonitoring = lazy(() => import('./pages/SNMPStorageMonitoring'))
const SNMPVLANMonitoring = lazy(() => import('./pages/SNMPVLANMonitoring'))

/** All SNMP URLs live under this feature route table. */
export const snmpRoutes = [
  { path: 'snmp', Component: withPermission(SNMPMonitoring, 'devices:read') },
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
