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
import Organizations from './pages/Organizations'
import Vendors from './pages/Vendors'
import Sites from './pages/Sites'
import DailyReport from './pages/DailyReport'
import ErrorPage from './pages/ErrorPage'

import SNMPDashboard from './pages/SNMPDashboard'

// New DB-First SNMP Pages
import SNMPDevices from './pages/SNMPDevices'
import SNMPDeviceDetails from './pages/SNMPDeviceDetails'
import SNMPMonitoringConfig from './pages/SNMPMonitoringConfig'

// Module-based SNMP Pages
import SNMPCPUMonitoring from './pages/SNMPCPUMonitoring'
import SNMPMemoryMonitoring from './pages/SNMPMemoryMonitoring'
import SNMPInterfaceMonitoring from './pages/SNMPInterfaceMonitoring'
import SNMPStorageMonitoring from './pages/SNMPStorageMonitoring'
import SNMPEnvironmentMonitoring from './pages/SNMPEnvironmentMonitoring'
import SNMPVLANMonitoring from './pages/SNMPVLANMonitoring'
import SNMPLLDPMonitoring from './pages/SNMPLLDPMonitoring'
import SNMPRoutingMonitoring from './pages/SNMPRoutingMonitoring'
import SNMPTopologyMonitoring from './pages/SNMPTopologyMonitoring'
import SNMPOIDExplorer from './pages/SNMPOIDExplorer'
import SNMPPollingMonitoring from './pages/SNMPPollingMonitoring'
import SNMPCapabilities from './pages/SNMPCapabilities'

// New CRUD Pages
import AlertsManagement from './pages/AlertsManagement'
import Events from './pages/Events'
import Notifications from './pages/Notifications'
import AuditLogs from './pages/AuditLogs'
import Thresholds from './pages/Thresholds'
import MonitoringJobs from './pages/MonitoringJobs'
import DeviceCredentials from './pages/DeviceCredentials'
import DeviceTypes from './pages/DeviceTypes'
import InterfacesList from './pages/InterfacesList'

export const router = createBrowserRouter([
  {
    path: '/login',
    Component: Login,
  },
  {
    path: '/unauthorized',
    Component: Unauthorized,
  },
  {
    Component: ProtectedLayout,
    errorElement: <ErrorPage />,
    children: [
      {
        path: '/',
        Component: Layout,
        errorElement: <ErrorPage />,
        children: [
          { index: true, Component: withPermission(Dashboard, 'dashboard:read') },
          { path: 'topology', Component: withPermission(Topology, 'topology:read') },
          { path: 'isp', Component: withPermission(ISPMonitoring, 'isp:read') },
          { path: 'incidents', Component: withPermission(Incidents, 'incidents:read') },
          { path: 'alerts', Component: withPermission(AlertsManagement, 'alerts:read') },
          { path: 'packet-analysis', Component: withPermission(PacketAnalysis, 'packet_analysis:read') },
          { path: 'nginx', Component: withPermission(NginxMonitoring, 'nginx:read') },
          { path: 'firewall', Component: withPermission(Firewall, 'firewall:read') },
          { path: 'snmp', Component: withPermission(SNMPMonitoring, 'devices:read') },
          { path: 'snmp-monitoring', Component: withPermission(SNMPMonitoring, 'devices:read') },
          
          // New DB-First SNMP Routes
          { path: 'snmp/dashboard', Component: withPermission(SNMPDashboard, 'devices:read') },
          { path: 'snmp/dashboard/:deviceId', Component: withPermission(SNMPDashboard, 'devices:read') },
          { path: 'snmp/devices', Component: withPermission(SNMPDevices, 'devices:read') },
          { path: 'snmp/devices/:deviceId', Component: withPermission(SNMPDeviceDetails, 'devices:read') },
          { path: 'snmp/devices/:deviceId/monitoring', Component: withPermission(SNMPMonitoringConfig, 'devices:update') },
          
          // Module-based SNMP Routes (dynamic - only show if supported)
          { path: 'snmp/devices/:deviceId/cpu', Component: withPermission(SNMPCPUMonitoring, 'devices:read') },
          { path: 'snmp/devices/:deviceId/memory', Component: withPermission(SNMPMemoryMonitoring, 'devices:read') },
          { path: 'snmp/devices/:deviceId/interfaces', Component: withPermission(SNMPInterfaceMonitoring, 'devices:read') },
          { path: 'snmp/devices/:deviceId/storage', Component: withPermission(SNMPStorageMonitoring, 'devices:read') },
          { path: 'snmp/devices/:deviceId/environment', Component: withPermission(SNMPEnvironmentMonitoring, 'devices:read') },
          { path: 'snmp/devices/:deviceId/vlan', Component: withPermission(SNMPVLANMonitoring, 'devices:read') },
          { path: 'snmp/devices/:deviceId/lldp', Component: withPermission(SNMPLLDPMonitoring, 'devices:read') },
          { path: 'snmp/devices/:deviceId/routing', Component: withPermission(SNMPRoutingMonitoring, 'devices:read') },
          { path: 'snmp/devices/:deviceId/topology', Component: withPermission(SNMPTopologyMonitoring, 'devices:read') },
          { path: 'snmp/devices/:deviceId/oids', Component: withPermission(SNMPOIDExplorer, 'devices:read') },
          { path: 'snmp/devices/:deviceId/polling', Component: withPermission(SNMPPollingMonitoring, 'devices:read') },
          { path: 'snmp/devices/:deviceId/capabilities', Component: withPermission(SNMPCapabilities, 'devices:read') },
          
          // Additional common routes
          { path: 'snmp/capabilities', Component: withPermission(SNMPCapabilities, 'devices:read') },
          { path: 'snmp/capabilities/:deviceId', Component: withPermission(SNMPCapabilities, 'devices:read') },
          
          { path: 'servers', Component: withPermission(ServerMonitoring, 'server_monitoring:read') },
          { path: 'forensics', Component: withPermission(Forensics, 'forensics:read') },
          { path: 'compliance', Component: withPermission(Compliance, 'compliance:read') },
          { path: 'device-monitoring', Component: withPermission(DeviceMonitoringList, 'device_monitoring:read') },
          { path: 'device-monitoring/:deviceId', Component: withPermission(DeviceMonitoring, 'device_monitoring:read') },
          { path: 'roles', Component: withPermission(RoleManagement, 'roles:read') },
          { path: 'users', Component: withPermission(UserManagement, 'users:read') },
          { path: 'organizations', Component: withPermission(Organizations, 'organizations:read') },
          { path: 'vendors', Component: withPermission(Vendors, 'vendors:read') },
          { path: 'reports/daily', Component: withPermission(DailyReport, 'reports:read') },
          { path: 'sites', Component: withPermission(Sites, 'sites:read') },
          
          // New CRUD Management Pages
          { path: 'alerts-management', Component: withPermission(AlertsManagement, 'alerts:read') },
          { path: 'events', Component: withPermission(Events, 'events:read') },
          { path: 'notifications', Component: withPermission(Notifications, 'notifications:read') },
          { path: 'audit-logs', Component: withPermission(AuditLogs, 'audit_logs:read') },
          { path: 'thresholds', Component: withPermission(Thresholds, 'thresholds:read') },
          { path: 'monitoring-jobs', Component: withPermission(MonitoringJobs, 'monitoring_jobs:read') },
          { path: 'device-credentials', Component: withPermission(DeviceCredentials, 'device_credentials:read') },
          { path: 'device-types', Component: withPermission(DeviceTypes, 'device_types:read') },
          { path: 'interfaces', Component: withPermission(InterfacesList, 'interfaces:read') },
          
          { path: '*', Component: ErrorPage },
        ],
      },
    ],
  },
  {
    path: '*',
    Component: ErrorPage,
  },
])