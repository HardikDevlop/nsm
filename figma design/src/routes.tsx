import { lazy } from 'react'
import { createBrowserRouter } from 'react-router'
import Layout from './components/Layout'
import ProtectedLayout from './components/ProtectedLayout'
import { withPermission } from './components/ProtectedLayout'
import ErrorPage from './pages/ErrorPage'
import { snmpRoutes } from './features/snmp/routes'

function lazyRetry<T extends { default: React.ComponentType<any> }>(loader: () => Promise<T>) {
  return lazy(async () => {
    try {
      return await loader()
    } catch (error) {
      // A transient dev-server/module-resolution failure can leave the route
      // tree unusable. Retry once before falling back to the page error UI.
      await new Promise(resolve => setTimeout(resolve, 120))
      return loader()
    }
  })
}

const Login = lazyRetry(() => import('./pages/Login'))
const Unauthorized = lazyRetry(() => import('./pages/Unauthorized'))
const Dashboard = lazyRetry(() => import('./pages/Dashboard'))
const Topology = lazyRetry(() => import('./pages/Topology'))
const ManualTopology = lazyRetry(() => import('./pages/ManualTopology'))
const ISPMonitoring = lazyRetry(() => import('./pages/ISPMonitoring'))
const Incidents = lazyRetry(() => import('./pages/Incidents'))
const PacketAnalysis = lazyRetry(() => import('./pages/PacketAnalysis'))
const LinuxServerMonitoring = lazyRetry(() => import('./pages/LinuxServerMonitoring'))
const DeviceMonitoring = lazyRetry(() => import('./pages/DeviceMonitoring'))
const DeviceMonitoringList = lazyRetry(() => import('./pages/DeviceMonitoringList'))
const RoleManagement = lazyRetry(() => import('./pages/RoleManagement'))
const UserManagement = lazyRetry(() => import('./pages/UserManagement'))
const Organizations = lazyRetry(() => import('./pages/Organizations'))
const Vendors = lazyRetry(() => import('./pages/Vendors'))
const Sites = lazyRetry(() => import('./pages/Sites'))
const DailyReport = lazyRetry(() => import('./pages/DailyReport'))
const ReportManagement = lazyRetry(() => import('./pages/ReportManagement'))
const AlertsManagement = lazyRetry(() => import('./pages/AlertsManagement'))
const Events = lazyRetry(() => import('./pages/Events'))
const Notifications = lazyRetry(() => import('./pages/Notifications'))
const AuditLogs = lazyRetry(() => import('./pages/AuditLogs'))
const Thresholds = lazyRetry(() => import('./pages/Thresholds'))
const MonitoringJobs = lazyRetry(() => import('./pages/MonitoringJobs'))
const DeviceCredentials = lazyRetry(() => import('./pages/DeviceCredentials'))
const DeviceTypes = lazyRetry(() => import('./pages/DeviceTypes'))
const InterfacesList = lazyRetry(() => import('./pages/InterfacesList'))
const FlowAnalytics = lazyRetry(() => import('./pages/FlowAnalytics'))
const APM = lazyRetry(() => import('./pages/APM'))
const CMDB = lazyRetry(() => import('./pages/CMDB'))
const RCA = lazyRetry(() => import('./pages/RCA'))
const IncidentManagement = lazyRetry(() => import('./pages/IncidentManagement'))
const ProblemManagement = lazyRetry(() => import('./pages/ProblemManagement'))
const ChangeManagement = lazyRetry(() => import('./pages/ChangeManagement'))
const KnowledgeBase = lazyRetry(() => import('./pages/KnowledgeBase'))
const ConfigurationBackups = lazyRetry(() => import('./pages/ConfigurationBackups'))
const ConfigurationCompliance = lazyRetry(() => import('./pages/ConfigurationCompliance'))
const Availability = lazyRetry(() => import('./pages/Availability'))
const QoS = lazyRetry(() => import('./pages/QoS'))
const BGP = lazyRetry(() => import('./pages/BGP'))

export const router = createBrowserRouter([
  { path: '/login', Component: Login },
  { path: '/unauthorized', Component: Unauthorized },
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
          { path: 'manual-topology', Component: withPermission(ManualTopology, 'topology:read') },
          { path: 'isp', Component: withPermission(ISPMonitoring, 'isp:read') },
          { path: 'incidents', Component: withPermission(Incidents, 'incidents:read') },
          { path: 'alerts', Component: withPermission(AlertsManagement, 'alerts:read') },
          { path: 'packet-analysis', Component: withPermission(PacketAnalysis, 'packet_analysis:read') },
          { path: 'flow-analytics', Component: withPermission(FlowAnalytics, 'flows:read') },
          { path: 'apm', Component: withPermission(APM, 'apm:read') },
          { path: 'cmdb', Component: withPermission(CMDB, 'cmdb:read') },
          { path: 'rca', Component: withPermission(RCA, 'rca:read') },
          { path: 'incident-management', Component: withPermission(IncidentManagement, 'incidents:read') },
          { path: 'problem-management', Component: withPermission(ProblemManagement, 'problems:read') },
          { path: 'change-management', Component: withPermission(ChangeManagement, 'changes:read') },
          { path: 'knowledge-base', Component: withPermission(KnowledgeBase, 'knowledge:read') },
          { path: 'configuration-backups', Component: withPermission(ConfigurationBackups, 'config_backups:read') },
          { path: 'configuration-compliance', Component: withPermission(ConfigurationCompliance, 'config_compliance:read') },
          { path: 'availability', Component: withPermission(Availability, 'availability:read') },
          { path: 'qos', Component: withPermission(QoS, 'qos:read') },
          { path: 'bgp', Component: withPermission(BGP, 'bgp:read') },
          ...snmpRoutes,
          { path: 'linux-servers', Component: withPermission(LinuxServerMonitoring, 'linux_servers:read') },
          { path: 'device-monitoring', Component: withPermission(DeviceMonitoringList, 'device_monitoring:read') },
          { path: 'device-monitoring/:deviceId', Component: withPermission(DeviceMonitoring, 'device_monitoring:read') },
          { path: 'roles', Component: withPermission(RoleManagement, 'roles:read') },
          { path: 'users', Component: withPermission(UserManagement, 'users:read') },
          { path: 'organizations', Component: withPermission(Organizations, 'organizations:read') },
          { path: 'vendors', Component: withPermission(Vendors, 'vendors:read') },
          { path: 'reports/daily', Component: withPermission(DailyReport, 'reports:read') },
          { path: 'reports/management', Component: withPermission(ReportManagement, 'reports:read') },
          { path: 'sites', Component: withPermission(Sites, 'sites:read') },
          { path: 'alerts-management', Component: withPermission(AlertsManagement, 'alerts:read') },
          { path: 'events', Component: withPermission(Events, 'events:read') },
          { path: 'notifications', Component: withPermission(Notifications, 'notifications:read') },
          { path: 'audit-logs', Component: withPermission(AuditLogs, 'audit_logs:read') },
          { path: 'monitoring-jobs', Component: withPermission(MonitoringJobs, 'monitoring_jobs:read') },
          { path: 'device-credentials', Component: withPermission(DeviceCredentials, 'device_credentials:read') },
          { path: 'device-types', Component: withPermission(DeviceTypes, 'device_types:read') },
          { path: 'interfaces', Component: withPermission(InterfacesList, 'interfaces:read') },
          { path: '*', Component: ErrorPage },
        ],
      },
    ],
  },
  { path: '*', Component: ErrorPage },
])
