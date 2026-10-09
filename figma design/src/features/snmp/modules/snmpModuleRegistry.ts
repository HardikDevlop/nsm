export interface SNMPModuleConfig {
  id: string;
  label: string;
  icon: string;
  color: string;
  route: string;
  apiEndpoint: string;
  queryKey: string[];
  supportedCheck: (capabilities: Record<string, boolean>) => boolean;
  summaryFields?: string[];
  tableColumns?: SNMPTableColumn[];
  chartConfig?: SNMPChartConfig;
  detailComponent?: string;
}

export interface SNMPTableColumn {
  key: string;
  label: string;
  sortable?: boolean;
  render?: (row: any) => React.ReactNode;
  type?: 'text' | 'status' | 'number' | 'bytes' | 'percent' | 'timestamp' | 'custom';
}

export interface SNMPChartConfig {
  dataKey: string;
  valueKey: string;
  color: string;
  unit: string;
  label: string;
  showArea?: boolean;
  height?: number;
}

export const SNMP_MODULES: Record<string, SNMPModuleConfig> = {
  system: {
    id: 'system',
    label: 'System',
    icon: 'M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z',
    color: '#00d4ff',
    route: '',
    apiEndpoint: '/snmp/devices/{deviceId}/system',
    queryKey: ['snmp', 'system'],
    supportedCheck: (caps) => caps.system !== false,
    summaryFields: ['hostname', 'description', 'mac_address', 'contact', 'location'],
  },
  cpu: {
    id: 'cpu',
    label: 'CPU',
    icon: 'M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z',
    color: '#00ff88',
    route: 'cpu',
    apiEndpoint: '/snmp/devices/{deviceId}/cpu',
    queryKey: ['snmp', 'cpu'],
    supportedCheck: (caps) => caps.cpu === true,
    summaryFields: ['current_usage', 'average', 'maximum', 'per_core'],
    chartConfig: {
      dataKey: 'history',
      valueKey: 'usage',
      color: '#00d4ff',
      unit: '%',
      label: 'CPU %',
      showArea: true,
      height: 200,
    },
    tableColumns: [
      { key: 'timestamp', label: 'Timestamp', sortable: true, type: 'timestamp' },
      { key: 'usage', label: 'CPU Usage', sortable: true, type: 'percent' },
      { key: 'health', label: 'Health', sortable: true, type: 'status' },
    ],
  },
  memory: {
    id: 'memory',
    label: 'Memory',
    icon: 'M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4',
    color: '#7c3aed',
    route: 'memory',
    apiEndpoint: '/snmp/devices/{deviceId}/memory',
    queryKey: ['snmp', 'memory'],
    supportedCheck: (caps) => caps.memory === true,
    summaryFields: ['total_bytes', 'used_bytes', 'free_bytes', 'utilization_percent', 'cached_bytes', 'buffer_bytes'],
    chartConfig: {
      dataKey: 'history',
      valueKey: 'utilization',
      color: '#7c3aed',
      unit: '%',
      label: 'Memory %',
      showArea: true,
      height: 200,
    },
    tableColumns: [
      { key: 'timestamp', label: 'Timestamp', sortable: true, type: 'timestamp' },
      { key: 'used', label: 'Used', sortable: true, type: 'bytes' },
      { key: 'free', label: 'Free', sortable: true, type: 'bytes' },
      { key: 'utilization', label: 'Utilization', sortable: true, type: 'percent' },
      { key: 'health', label: 'Health', sortable: true, type: 'status' },
    ],
  },
  storage: {
    id: 'storage',
    label: 'Storage',
    icon: 'M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4',
    color: '#ffaa00',
    route: 'storage',
    apiEndpoint: '/snmp/devices/{deviceId}/storage',
    queryKey: ['snmp', 'storage'],
    supportedCheck: (caps) => caps.storage === true,
    summaryFields: ['volumes'],
    tableColumns: [
      { key: 'mount_name', label: 'Mount Point', sortable: true },
      { key: 'type', label: 'Type', sortable: true },
      { key: 'total_bytes', label: 'Total', sortable: true, type: 'bytes' },
      { key: 'used_bytes', label: 'Used', sortable: true, type: 'bytes' },
      { key: 'free_bytes', label: 'Free', sortable: true, type: 'bytes' },
      { key: 'utilization_percent', label: 'Utilization', sortable: true, type: 'percent' },
      { key: 'health', label: 'Health', sortable: true, type: 'status' },
      { key: 'last_updated', label: 'Last Updated', sortable: true, type: 'timestamp' },
    ],
  },
  interfaces: {
    id: 'interfaces',
    label: 'Interfaces',
    icon: 'M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4',
    color: '#00bfff',
    route: 'interfaces',
    // This page reads the scheduler's last successful snapshot. The plain
    // /interfaces endpoint starts a blocking live SNMP walk and can return
    // 409 while the background poll is already running.
    apiEndpoint: '/snmp/devices/{deviceId}/interfaces/latest',
    queryKey: ['snmp', 'interfaces'],
    supportedCheck: (caps) => caps.interfaces === true,
    summaryFields: ['total', 'up', 'down'],
    tableColumns: [
      { key: 'name', label: 'Name', sortable: true },
      { key: 'description', label: 'Description', sortable: true },
      { key: 'status', label: 'Status', sortable: true, type: 'status' },
      { key: 'speed_bps', label: 'Speed', sortable: true, type: 'custom', render: (row) => formatSpeed(row.speed_bps) },
      { key: 'mac_address', label: 'MAC', sortable: true },
      { key: 'rx_mbps', label: 'RX', sortable: true, type: 'custom', render: (row) => formatRate(row.rx_mbps) },
      { key: 'tx_mbps', label: 'TX', sortable: true, type: 'custom', render: (row) => formatRate(row.tx_mbps) },
      { key: 'utilization_percent', label: 'Util %', sortable: true, type: 'percent' },
      { key: 'errors', label: 'Errors', sortable: true, type: 'number' },
      { key: 'discards', label: 'Discards', sortable: true, type: 'number' },
      { key: 'last_updated', label: 'Last Updated', sortable: true, type: 'timestamp' },
    ],
  },
  environment: {
    id: 'environment',
    label: 'Environment',
    icon: 'M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z',
    color: '#ff6644',
    route: 'environment',
    apiEndpoint: '/snmp/devices/{deviceId}/environment',
    queryKey: ['snmp', 'environment'],
    supportedCheck: (caps) => caps.environment === true,
    summaryFields: ['sensors'],
    tableColumns: [
      { key: 'sensor_name', label: 'Sensor Name', sortable: true },
      { key: 'sensor_type', label: 'Type', sortable: true },
      { key: 'current_value', label: 'Value', sortable: true, type: 'custom', render: (row) => formatSensorValue(row) },
      { key: 'unit', label: 'Unit', sortable: true },
      { key: 'status', label: 'Status', sortable: true, type: 'status' },
      { key: 'threshold_warning', label: 'Warn Threshold', sortable: true },
      { key: 'threshold_critical', label: 'Crit Threshold', sortable: true },
      { key: 'last_updated', label: 'Last Updated', sortable: true, type: 'timestamp' },
    ],
  },
  vlan: {
    id: 'vlan',
    label: 'VLAN',
    icon: 'M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10',
    color: '#34d399',
    route: 'vlan',
    apiEndpoint: '/snmp/devices/{deviceId}/vlans',
    queryKey: ['snmp', 'vlans'],
    supportedCheck: (caps) => caps.vlan === true,
    summaryFields: ['vlans'],
    tableColumns: [
      { key: 'vlan_id', label: 'VLAN ID', sortable: true, type: 'number' },
      { key: 'vlan_name', label: 'Name', sortable: true },
      { key: 'status', label: 'Status', sortable: true, type: 'status' },
      { key: 'tagged_ports', label: 'Tagged Ports', sortable: true },
      { key: 'untagged_ports', label: 'Untagged Ports', sortable: true },
      { key: 'last_updated', label: 'Last Updated', sortable: true, type: 'timestamp' },
    ],
  },
  lldp: {
    id: 'lldp',
    label: 'LLDP',
    icon: 'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z',
    color: '#a78bfa',
    route: 'lldp',
    apiEndpoint: '/snmp/devices/{deviceId}/lldp',
    queryKey: ['snmp', 'lldp'],
    supportedCheck: (caps) => caps.lldp === true,
    summaryFields: ['neighbors'],
    tableColumns: [
      { key: 'local_port', label: 'Local Interface', sortable: true },
      { key: 'remote_device', label: 'Remote Device', sortable: true },
      { key: 'remote_port', label: 'Remote Interface', sortable: true },
      { key: 'remote_system_name', label: 'System Name', sortable: true },
      { key: 'remote_mgmt_ip', label: 'Mgmt IP', sortable: true },
      { key: 'capabilities', label: 'Capabilities', sortable: true },
      { key: 'last_updated', label: 'Last Updated', sortable: true, type: 'timestamp' },
    ],
  },
  routing: {
    id: 'routing',
    label: 'Routing',
    icon: 'M13 10V3L4 14h7v7l9-11h-7z',
    color: '#f472b6',
    route: 'routing',
    apiEndpoint: '/snmp/devices/{deviceId}/routing',
    queryKey: ['snmp', 'routing'],
    supportedCheck: (caps) => caps.routing === true,
    summaryFields: ['routes'],
    tableColumns: [
      { key: 'destination', label: 'Destination', sortable: true },
      { key: 'next_hop', label: 'Next Hop', sortable: true },
      { key: 'interface', label: 'Interface', sortable: true },
      { key: 'metric', label: 'Metric', sortable: true, type: 'number' },
      { key: 'protocol', label: 'Protocol', sortable: true },
      { key: 'type', label: 'Type', sortable: true },
      { key: 'status', label: 'Status', sortable: true, type: 'status' },
      { key: 'last_updated', label: 'Last Updated', sortable: true, type: 'timestamp' },
    ],
  },
  cdp: {
    id: 'cdp',
    label: 'CDP',
    icon: 'M17 20h5v-2a3 3 0 00-5.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M15 7a3 3 0 11-6 0 3 3 0 016 0z',
    color: '#22d3ee',
    route: 'cdp',
    apiEndpoint: '/snmp/devices/{deviceId}/cdp',
    queryKey: ['snmp', 'cdp'],
    supportedCheck: (caps) => caps.cdp === true,
    summaryFields: ['neighbors'],
  },
  arp: {
    id: 'arp',
    label: 'ARP',
    icon: 'M4 7h16M4 12h16M4 17h16',
    color: '#fb7185',
    route: 'arp',
    apiEndpoint: '/snmp/devices/{deviceId}/arp',
    queryKey: ['snmp', 'arp'],
    supportedCheck: (caps) => caps.arp === true,
    summaryFields: ['entries'],
  },
  mac_table: {
    id: 'mac_table',
    label: 'MAC Table',
    icon: 'M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01',
    color: '#38bdf8',
    route: 'mac_table',
    apiEndpoint: '/snmp/devices/{deviceId}/mac-table',
    queryKey: ['snmp', 'mac-table'],
    supportedCheck: (caps) => caps.mac_table === true,
    summaryFields: ['entries'],
  },
  firewall: {
    id: 'firewall',
    label: 'Firewall',
    icon: 'M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z',
    color: '#f43f5e',
    route: 'firewall',
    apiEndpoint: '/snmp/devices/{deviceId}/firewall',
    queryKey: ['snmp', 'firewall'],
    supportedCheck: (caps) => caps.firewall === true,
    summaryFields: ['sessions', 'policies'],
  },
  wireless: {
    id: 'wireless',
    label: 'Wireless',
    icon: 'M5 12.55a11 11 0 0114.08 0M8.5 16.05a6 6 0 017 0M12 20h.01',
    color: '#2dd4bf',
    route: 'wireless',
    apiEndpoint: '/snmp/devices/{deviceId}/wireless',
    queryKey: ['snmp', 'wireless'],
    supportedCheck: (caps) => caps.wireless === true,
    summaryFields: ['ssids', 'clients'],
  },
  inventory: {
    id: 'inventory',
    label: 'Inventory',
    icon: 'M3 7h18M5 7v12h14V7M9 11h6',
    color: '#eab308',
    route: 'inventory',
    apiEndpoint: '/snmp/devices/{deviceId}/inventory',
    queryKey: ['snmp', 'inventory'],
    supportedCheck: (caps) => caps.inventory === true,
    summaryFields: ['total_count', 'fru_count', 'port_count', 'loader_date', 'system_uptime', 'loader_version', 'firmware_version'],
  },
  health: {
    id: 'health',
    label: 'Health',
    icon: 'M20 6L9 17l-5-5',
    color: '#00ff88',
    route: 'health',
    apiEndpoint: '/snmp/devices/{deviceId}/health',
    queryKey: ['snmp', 'health'],
    supportedCheck: (caps) => caps.health !== false,
    summaryFields: ['status', 'reachable', 'snmp_enabled', 'alarm_count'],
  },
  topology: {
    id: 'topology',
    label: 'Topology',
    icon: 'M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9',
    color: '#6366f1',
    route: 'topology',
    apiEndpoint: '/snmp/devices/{deviceId}/device-topology',
    queryKey: ['snmp', 'topology'],
    supportedCheck: (caps) => caps.topology === true || caps.lldp === true,
    summaryFields: ['devices', 'links'],
  },
  oids: {
    id: 'oids',
    label: 'OID Explorer',
    icon: 'M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z',
    color: '#14b8a6',
    route: 'oids',
    apiEndpoint: '/snmp/devices/{deviceId}/oids',
    queryKey: ['snmp', 'oids'],
    supportedCheck: (caps) => caps.oids === true || caps.inventory === true,
    summaryFields: ['oids'],
    tableColumns: [
      { key: 'oid', label: 'OID', sortable: true },
      { key: 'oid_name', label: 'Name', sortable: true },
      { key: 'supported', label: 'Supported', sortable: true, type: 'status' },
      { key: 'vendor_specific', label: 'Vendor Specific', sortable: true, type: 'status' },
      { key: 'last_seen', label: 'Last Seen', sortable: true, type: 'timestamp' },
    ],
  },
  polling: {
    id: 'polling',
    label: 'Polling',
    icon: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z',
    color: '#f97316',
    route: 'polling',
    apiEndpoint: '/snmp/devices/{deviceId}/polling-history',
    queryKey: ['snmp', 'polling-history'],
    supportedCheck: (caps) => true,
    summaryFields: ['history'],
    tableColumns: [
      { key: 'timestamp', label: 'Timestamp', sortable: true, type: 'timestamp' },
      { key: 'collector', label: 'Module', sortable: true },
      { key: 'status', label: 'Status', sortable: true, type: 'status' },
      { key: 'duration_ms', label: 'Duration (ms)', sortable: true, type: 'number' },
      { key: 'error', label: 'Error', sortable: true },
    ],
  },
};

export const MODULE_ORDER = [
  'system',
  'cpu',
  'memory',
  'storage',
  'interfaces',
  'environment',
  'vlan',
  'lldp',
  'cdp',
  'routing',
  'arp',
  'mac_table',
  'firewall',
  'wireless',
  'inventory',
  'topology',
  'health',
  'oids',
  'polling',
];

export const INTERVAL_OPTIONS = [15, 30, 60, 120, 300, 600];

export function getSupportedModules(capabilities: Record<string, boolean>): SNMPModuleConfig[] {
  return MODULE_ORDER
    .map((id) => SNMP_MODULES[id])
    .filter((module) => module.supportedCheck(capabilities));
}

export function getSupportedModuleConfigs(capabilities: Record<string, boolean>): SNMPModuleConfig[] {
  return getSupportedModules(capabilities);
}

export function getModuleConfig(moduleId: string): SNMPModuleConfig | undefined {
  return SNMP_MODULES[moduleId];
}

export function formatBytes(bytes: number | undefined | null): string {
  if (!bytes || bytes === 0) return '—';
  const abs = Math.abs(bytes);
  if (abs >= 1_099_511_627_776) return `${(bytes / 1_099_511_627_776).toFixed(2)} TB`;
  if (abs >= 1_073_741_824) return `${(bytes / 1_073_741_824).toFixed(2)} GB`;
  if (abs >= 1_048_576) return `${(bytes / 1_048_576).toFixed(1)} MB`;
  if (abs >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
}

export function formatSpeed(bps: number | undefined | null): string {
  if (bps === undefined || bps === null || !Number.isFinite(Number(bps)) || Number(bps) === 0) return '—';
  bps = Number(bps);
  if (bps >= 1_000_000_000) return `${(bps / 1_000_000_000).toFixed(1)} Gbps`;
  if (bps >= 1_000_000) return `${(bps / 1_000_000).toFixed(1)} Mbps`;
  if (bps >= 1000) return `${(bps / 1000).toFixed(1)} Kbps`;
  return `${bps} bps`;
}

export function formatRate(mbps: number | undefined | null): string {
  if (mbps === undefined || mbps === null || !Number.isFinite(Number(mbps))) return '—';
  return `${Number(mbps).toFixed(2)} Mbps`;
}

export function formatSensorValue(sensor: any): string {
  if (sensor.current_value === undefined || sensor.current_value === null) return '—';
  const unit = sensor.unit || '';
  return `${sensor.current_value.toFixed(1)}${unit}`;
}

export function getHealthColor(health: string): string {
  switch (health) {
    case 'healthy':
    case 'ok':
      return '#00ff88';
    case 'warning':
    case 'warn':
      return '#ffaa00';
    case 'critical':
    case 'error':
      return '#ff3366';
    default:
      return '#8899bb';
  }
}

export function getStatusColor(status: string): string {
  const normalized = status.toLowerCase();
  if (normalized === 'up' || normalized === 'ok' || normalized === 'healthy' || normalized === 'active' || normalized === 'running' || normalized === 'supported') {
    return '#00ff88';
  }
  if (normalized === 'down' || normalized === 'critical' || normalized === 'error' || normalized === 'failed' || normalized === 'stopped') {
    return '#ff3366';
  }
  if (normalized === 'warning' || normalized === 'warn') {
    return '#ffaa00';
  }
  return '#8899bb';
}
