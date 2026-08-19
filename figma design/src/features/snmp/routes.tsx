import { withPermission } from '../../components/ProtectedLayout'
import AddSNMPDevice from './pages/AddSNMPDevice'
import SNMPCapabilities from './pages/SNMPCapabilities'
import SNMPCPUMonitoring from './pages/SNMPCPUMonitoring'
import SNMPDashboard from './pages/SNMPDashboard'
import SNMPDeviceDetails from './pages/SNMPDeviceDetails'
import SNMPDevices from './pages/SNMPDevices'
import SNMPEnvironmentMonitoring from './pages/SNMPEnvironmentMonitoring'
import SNMPGenericModulePage from './pages/SNMPGenericModulePage'
import SNMPInterfaceDetails from './pages/SNMPInterfaceDetails'
import SNMPInterfaceMonitoring from './pages/SNMPInterfaceMonitoring'
import SNMPLLDPMonitoring from './pages/SNMPLLDPMonitoring'
import SNMPMemoryMonitoring from './pages/SNMPMemoryMonitoring'
import SNMPMonitoring from './pages/SNMPMonitoring'
import SNMPMonitoringConfig from './pages/SNMPMonitoringConfig'
import SNMPOIDExplorer from './pages/SNMPOIDExplorer'
import SNMPPollingMonitoring from './pages/SNMPPollingMonitoring'
import SNMPRoutingMonitoring from './pages/SNMPRoutingMonitoring'
import SNMPStorageMonitoring from './pages/SNMPStorageMonitoring'
import SNMPVLANMonitoring from './pages/SNMPVLANMonitoring'

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
