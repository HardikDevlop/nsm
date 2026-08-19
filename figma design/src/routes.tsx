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

import { snmpRoutes } from './features/snmp/routes'

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
          ...snmpRoutes,
          
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
