import { createBrowserRouter } from 'react-router'
import Layout from './components/Layout'
import ProtectedLayout from './components/ProtectedLayout'
import { withPermission } from './components/ProtectedLayout'
import Login from './pages/Login'
import Unauthorized from './pages/Unauthorized'
import Dashboard from './pages/Dashboard'
import Topology from './pages/Topology'
import ISPMonitoring from './pages/ISPMonitoring'
import Incidents from './pages/Incidents'
// import AttackPath from './pages/AttackPath'
import PacketAnalysis from './pages/PacketAnalysis'
import NginxMonitoring from './pages/NginxMonitoring'
import Firewall from './pages/Firewall'
import SNMPMonitoring from './pages/SNMPMonitoring'
import ServerMonitoring from './pages/ServerMonitoring'
import Forensics from './pages/Forensics'
import Compliance from './pages/Compliance'
import DeviceMonitoring from './pages/DeviceMonitoring'
import DeviceMonitoringList from './pages/DeviceMonitoringList'
import RoleManagement from './pages/RoleManagement'
import UserManagement from './pages/UserManagement'

// Enterprise SNMP Monitoring Pages
import SNMPDashboard from './pages/SNMPDashboard'
import SNMPCPUMonitoring from './pages/SNMPCPUMonitoring'
import SNMPMemoryMonitoring from './pages/SNMPMemoryMonitoring'
import SNMPInterfaceMonitoring from './pages/SNMPInterfaceMonitoring'
import SNMPStorageMonitoring from './pages/SNMPStorageMonitoring'
import SNMPEnvironmentMonitoring from './pages/SNMPEnvironmentMonitoring'
import SNMPTopologyMonitoring from './pages/SNMPTopologyMonitoring'
import SNMPOIDExplorer from './pages/SNMPOIDExplorer'
import SNMPPollingMonitoring from './pages/SNMPPollingMonitoring'

export const router = createBrowserRouter([
  // Public routes (no auth required)
  { path: '/login', Component: Login },
  { path: '/unauthorized', Component: Unauthorized },

  // Protected routes (auth required)
  {
    Component: ProtectedLayout,
    children: [
      {
        path: '/',
        Component: Layout,
        children: [
          { index: true, Component: withPermission(Dashboard, 'dashboard:read') },
          { path: 'topology', Component: withPermission(Topology, 'topology:read') },
          { path: 'isp', Component: withPermission(ISPMonitoring, 'isp:read') },
          { path: 'incidents', Component: withPermission(Incidents, 'incidents:read') },
          { path: 'alerts', Component: withPermission(Incidents, 'incidents:read') },
          // { path: 'attack-path', Component: withPermission(AttackPath, 'attack_path:read') },
          { path: 'packet-analysis', Component: withPermission(PacketAnalysis, 'packet_analysis:read') },
          { path: 'nginx', Component: withPermission(NginxMonitoring, 'nginx:read') },
          { path: 'firewall', Component: withPermission(Firewall, 'firewall:read') },
          { path: 'snmp', Component: withPermission(SNMPMonitoring, 'devices:read') },
          { path: 'snmp-monitoring', Component: withPermission(SNMPMonitoring, 'devices:read') },
          
          // Enterprise SNMP Monitoring Routes
          { path: 'snmp/dashboard', Component: withPermission(SNMPDashboard, 'devices:read') },
          { path: 'snmp/dashboard/:deviceId', Component: withPermission(SNMPDashboard, 'devices:read') },
          { path: 'snmp/cpu/:deviceId', Component: withPermission(SNMPCPUMonitoring, 'devices:read') },
          { path: 'snmp/memory/:deviceId', Component: withPermission(SNMPMemoryMonitoring, 'devices:read') },
          { path: 'snmp/interfaces/:deviceId', Component: withPermission(SNMPInterfaceMonitoring, 'devices:read') },
          { path: 'snmp/storage/:deviceId', Component: withPermission(SNMPStorageMonitoring, 'devices:read') },
          { path: 'snmp/environment/:deviceId', Component: withPermission(SNMPEnvironmentMonitoring, 'devices:read') },
          { path: 'snmp/topology/:deviceId', Component: withPermission(SNMPTopologyMonitoring, 'devices:read') },
          { path: 'snmp/topology', Component: withPermission(SNMPTopologyMonitoring, 'devices:read') },
          { path: 'snmp/oids/:deviceId', Component: withPermission(SNMPOIDExplorer, 'devices:read') },
          { path: 'snmp/polling/:deviceId', Component: withPermission(SNMPPollingMonitoring, 'devices:read') },
          { path: 'snmp/statistics/:deviceId', Component: withPermission(SNMPPollingMonitoring, 'devices:read') },
          
          { path: 'servers', Component: withPermission(ServerMonitoring, 'server_monitoring:read') },
          { path: 'forensics', Component: withPermission(Forensics, 'forensics:read') },
          { path: 'compliance', Component: withPermission(Compliance, 'compliance:read') },
          { path: 'device-monitoring', Component: withPermission(DeviceMonitoringList, 'device_monitoring:read') },
          { path: 'device-monitoring/:deviceId', Component: withPermission(DeviceMonitoring, 'device_monitoring:read') },
          { path: 'roles', Component: withPermission(RoleManagement, 'roles:read') },
          { path: 'users', Component: withPermission(UserManagement, 'users:read') },
        ],
      },
    ],
  },
])
