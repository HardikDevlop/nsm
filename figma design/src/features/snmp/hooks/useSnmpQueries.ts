import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  listSNMPDevicesOptimized,
  getSNMPDeviceDetails,
  getSNMPDeviceMonitoringConfigs,
  startModuleMonitoring,
  stopModuleMonitoring,
  updateModuleMonitoring,
  getModuleMonitoringStatus,
  getLatestMetrics,
  getLatestCPU,
  getLatestMemory,
  getLatestInterfaces,
  getLatestStorage,
  getLatestEnvironment,
  getSNMPMemoryStats,
  getSNMPInterfaces,
  getSNMPInterfaceHistory,
  getSNMPStorageStats,
  getSNMPEnvironmentStats,
  getSNMPVLANs,
  getSNMPLLDPNeighbors,
  getSNMPRoutingTable,
  getSNMPTopology,
  getSNMPOIDCache,
  getSNMPOIDTree,
  getSNMPPollingHistory,
  getSNMPPollingStatistics,
  addSNMPDevice,
  testSNMPConnection,
  discoverDevice,
  SNMPDevicesResponse,
  SNMPDeviceDetails,
  MonitoringConfig,
  LatestCPU,
  LatestMemory,
  LatestInterface,
  LatestStorage,
  LatestEnvironment,
  SNMPMemoryStats,
  SNMPInterfaceStats,
  SNMPInterfaceHistory,
  SNMPStorageStats,
  SNMPEnvironmentStats,
  SNMPVLANInfo,
  SNMPLLDPNeighbor,
  SNMPRoutingEntry,
  SNMPTopologyGraph,
  SNMPOIDCacheEntry,
  SNMPOIDTree,
  SNMPPollingHistory,
  SNMPPollingStatistics,
  AddDeviceRequest,
  AddDeviceResponse,
  SNMPTestResponse,
  SNMPDiscoverResponse,
} from '../../../lib/api';

// Query keys
export const snmpKeys = {
  devices: (params: Record<string, any>) => ['snmp', 'devices', params] as const,
  device: (deviceId: number) => ['snmp', 'device', deviceId] as const,
  monitoringConfigs: (deviceId: number) => ['snmp', 'monitoring', deviceId] as const,
  monitoringStatus: (deviceId: number, module: string) => ['snmp', 'monitoring', deviceId, module] as const,
  latestMetrics: (deviceId: number) => ['snmp', 'metrics', 'latest', deviceId] as const,
  latestCPU: (deviceId: number) => ['snmp', 'metrics', 'cpu', deviceId] as const,
  latestMemory: (deviceId: number) => ['snmp', 'metrics', 'memory', deviceId] as const,
  latestInterfaces: (deviceId: number) => ['snmp', 'metrics', 'interfaces', deviceId] as const,
  latestStorage: (deviceId: number) => ['snmp', 'metrics', 'storage', deviceId] as const,
  latestEnvironment: (deviceId: number) => ['snmp', 'metrics', 'environment', deviceId] as const,
  memoryStats: (deviceId: number) => ['snmp', 'memory', deviceId] as const,
  interfaces: (deviceId: number) => ['snmp', 'interfaces', deviceId] as const,
  interfaceHistory: (interfaceId: number, hours: number) => ['snmp', 'interface', interfaceId, 'history', hours] as const,
  storageStats: (deviceId: number) => ['snmp', 'storage', deviceId] as const,
  environmentStats: (deviceId: number) => ['snmp', 'environment', deviceId] as const,
  vlans: (deviceId: number) => ['snmp', 'vlans', deviceId] as const,
  lldpNeighbors: (deviceId: number) => ['snmp', 'lldp', deviceId] as const,
  routingTable: (deviceId: number) => ['snmp', 'routing', deviceId] as const,
  topology: (deviceId?: number) => ['snmp', 'topology', deviceId] as const,
  oidCache: (deviceId: number) => ['snmp', 'oids', deviceId] as const,
  oidTree: (deviceId: number) => ['snmp', 'oidTree', deviceId] as const,
  pollingHistory: (deviceId: number, hours: number) => ['snmp', 'pollingHistory', deviceId, hours] as const,
  pollingStatistics: (deviceId: number) => ['snmp', 'pollingStats', deviceId] as const,
};

// Device list with pagination, search, filtering
export function useSNMPDevices(params: {
  page?: number
  page_size?: number
  search?: string
  status?: string
  snmp_status?: string
  monitoring_status?: string
  device_type?: string
  vendor?: string
  model?: string
  hostname?: string
  sort_by?: string
  sort_order?: string
} = {}) {
  return useQuery<SNMPDevicesResponse>({
    queryKey: snmpKeys.devices(params),
    queryFn: () => listSNMPDevicesOptimized(params),
    placeholderData: (previousData) => previousData, // Keep previous data while fetching
  });
}

// Device details (DB-backed, no live SNMP)
export function useSNMPDeviceDetails(deviceId: number | null) {
  return useQuery<SNMPDeviceDetails>({
    queryKey: snmpKeys.device(deviceId!),
    queryFn: () => getSNMPDeviceDetails(deviceId!),
    enabled: !!deviceId,
    staleTime: 10000,
  });
}

// Monitoring configurations for a device
export function useMonitoringConfigs(deviceId: number | null) {
  return useQuery<MonitoringConfig[]>({
    queryKey: snmpKeys.monitoringConfigs(deviceId!),
    queryFn: () => getSNMPDeviceMonitoringConfigs(deviceId!),
    enabled: !!deviceId,
    staleTime: 30000,
  });
}

// Single module monitoring status
export function useModuleMonitoringStatus(deviceId: number | null, module: string | null) {
  return useQuery<MonitoringConfig>({
    queryKey: snmpKeys.monitoringStatus(deviceId!, module!),
    queryFn: () => getModuleMonitoringStatus(deviceId!, module!),
    enabled: !!deviceId && !!module,
    staleTime: 10000, // 10 seconds
  });
}

// Latest metrics (for dashboard/overview)
export function useLatestMetrics(deviceId: number | null) {
  return useQuery({
    queryKey: snmpKeys.latestMetrics(deviceId!),
    queryFn: () => getLatestMetrics(deviceId!),
    enabled: !!deviceId,
    staleTime: 30000,
  });
}

export function useLatestCPU(deviceId: number | null) {
  return useQuery<LatestCPU>({
    queryKey: snmpKeys.latestCPU(deviceId!),
    queryFn: () => getLatestCPU(deviceId!),
    enabled: !!deviceId,
    staleTime: 30000,
  });
}

export function useLatestMemory(deviceId: number | null) {
  return useQuery<LatestMemory>({
    queryKey: snmpKeys.latestMemory(deviceId!),
    queryFn: () => getLatestMemory(deviceId!),
    enabled: !!deviceId,
    staleTime: 30000,
  });
}

export function useLatestInterfaces(deviceId: number | null) {
  return useQuery<LatestInterface[]>({
    queryKey: snmpKeys.latestInterfaces(deviceId!),
    queryFn: () => getLatestInterfaces(deviceId!),
    enabled: !!deviceId,
    staleTime: 30000,
  });
}

export function useLatestStorage(deviceId: number | null) {
  return useQuery<LatestStorage[]>({
    queryKey: snmpKeys.latestStorage(deviceId!),
    queryFn: () => getLatestStorage(deviceId!),
    enabled: !!deviceId,
    staleTime: 30000,
  });
}

export function useLatestEnvironment(deviceId: number | null) {
  return useQuery<LatestEnvironment[]>({
    queryKey: snmpKeys.latestEnvironment(deviceId!),
    queryFn: () => getLatestEnvironment(deviceId!),
    enabled: !!deviceId,
    staleTime: 30000,
  });
}

// Memory Stats
export function useSNMPMemoryStats(deviceId: number | null) {
  return useQuery<SNMPMemoryStats>({
    queryKey: snmpKeys.memoryStats(deviceId!),
    queryFn: () => getSNMPMemoryStats(deviceId!),
    enabled: !!deviceId,
    staleTime: 30000,
  });
}

// Interfaces
export function useSNMPInterfaces(deviceId: number | null) {
  return useQuery<SNMPInterfaceStats[]>({
    queryKey: snmpKeys.interfaces(deviceId!),
    queryFn: () => getSNMPInterfaces(deviceId!),
    enabled: !!deviceId,
    staleTime: 30000,
  });
}

export function useSNMPInterfaceHistory(interfaceId: number | null, hours = 24) {
  return useQuery<SNMPInterfaceHistory>({
    queryKey: snmpKeys.interfaceHistory(interfaceId!, hours),
    queryFn: () => getSNMPInterfaceHistory(interfaceId!, hours),
    enabled: !!interfaceId,
    staleTime: 30000,
  });
}

// Storage
export function useSNMPStorageStats(deviceId: number | null) {
  return useQuery<SNMPStorageStats>({
    queryKey: snmpKeys.storageStats(deviceId!),
    queryFn: () => getSNMPStorageStats(deviceId!),
    enabled: !!deviceId,
    staleTime: 30000,
  });
}

// Environment
export function useSNMPEnvironmentStats(deviceId: number | null) {
  return useQuery<SNMPEnvironmentStats>({
    queryKey: snmpKeys.environmentStats(deviceId!),
    queryFn: () => getSNMPEnvironmentStats(deviceId!),
    enabled: !!deviceId,
    staleTime: 30000,
  });
}

// VLANs
export function useSNMPVLANs(deviceId: number | null) {
  return useQuery<SNMPVLANInfo[]>({
    queryKey: snmpKeys.vlans(deviceId!),
    queryFn: () => getSNMPVLANs(deviceId!),
    enabled: !!deviceId,
    staleTime: 60000,
  });
}

// LLDP Neighbors
export function useSNMPLLDPNeighbors(deviceId: number | null) {
  return useQuery<SNMPLLDPNeighbor[]>({
    queryKey: snmpKeys.lldpNeighbors(deviceId!),
    queryFn: () => getSNMPLLDPNeighbors(deviceId!),
    enabled: !!deviceId,
    staleTime: 60000,
  });
}

// Routing Table
export function useSNMPRoutingTable(deviceId: number | null) {
  return useQuery<SNMPRoutingEntry[]>({
    queryKey: snmpKeys.routingTable(deviceId!),
    queryFn: () => getSNMPRoutingTable(deviceId!),
    enabled: !!deviceId,
    staleTime: 60000,
  });
}

// Topology
export function useSNMPTopology(deviceId?: number | null) {
  return useQuery<SNMPTopologyGraph>({
    queryKey: snmpKeys.topology(deviceId!),
    queryFn: () => getSNMPTopology(deviceId ?? undefined),
    enabled: !!deviceId,
    staleTime: 60000,
  });
}

// OID Explorer
export function useSNMPOIDCache(deviceId: number | null) {
  return useQuery<SNMPOIDCacheEntry[]>({
    queryKey: snmpKeys.oidCache(deviceId!),
    queryFn: () => getSNMPOIDCache(deviceId!),
    enabled: !!deviceId,
    staleTime: 60000,
  });
}

export function useSNMPOIDTree(deviceId: number | null) {
  return useQuery<SNMPOIDTree>({
    queryKey: snmpKeys.oidTree(deviceId!),
    queryFn: () => getSNMPOIDTree(deviceId!),
    enabled: !!deviceId,
    staleTime: 60000,
  });
}

// Polling History & Statistics
export function useSNMPPollingHistory(deviceId: number | null, hours = 24) {
  return useQuery<SNMPPollingHistory[]>({
    queryKey: snmpKeys.pollingHistory(deviceId!, hours),
    queryFn: () => getSNMPPollingHistory(deviceId!, hours),
    enabled: !!deviceId,
    staleTime: 30000,
  });
}

export function useSNMPPollingStatistics(deviceId: number | null) {
  return useQuery<SNMPPollingStatistics>({
    queryKey: snmpKeys.pollingStatistics(deviceId!),
    queryFn: () => getSNMPPollingStatistics(deviceId!),
    enabled: !!deviceId,
    staleTime: 30000,
  });
}

// Mutations for monitoring control
export function useStartModuleMonitoring() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ deviceId, module, intervalSeconds }: { deviceId: number; module: string; intervalSeconds: number }) =>
      startModuleMonitoring(deviceId, module, intervalSeconds),
    onSuccess: (data, variables) => {
      // Invalidate monitoring configs and device details
      queryClient.invalidateQueries({ queryKey: snmpKeys.monitoringConfigs(variables.deviceId) });
      queryClient.invalidateQueries({ queryKey: snmpKeys.device(variables.deviceId) });
      queryClient.invalidateQueries({ queryKey: snmpKeys.monitoringStatus(variables.deviceId, variables.module) });
    },
  });
}

export function useStopModuleMonitoring() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ deviceId, module }: { deviceId: number; module: string }) =>
      stopModuleMonitoring(deviceId, module),
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ queryKey: snmpKeys.monitoringConfigs(variables.deviceId) });
      queryClient.invalidateQueries({ queryKey: snmpKeys.device(variables.deviceId) });
      queryClient.invalidateQueries({ queryKey: snmpKeys.monitoringStatus(variables.deviceId, variables.module) });
    },
  });
}

export function useUpdateModuleMonitoring() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ deviceId, module, data }: { deviceId: number; module: string; data: { enabled?: boolean; interval_seconds?: number } }) =>
      updateModuleMonitoring(deviceId, module, data),
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ queryKey: snmpKeys.monitoringConfigs(variables.deviceId) });
      queryClient.invalidateQueries({ queryKey: snmpKeys.device(variables.deviceId) });
      queryClient.invalidateQueries({ queryKey: snmpKeys.monitoringStatus(variables.deviceId, variables.module) });
    },
  });
}

// Device CRUD mutations
export function useAddSNMPDevice() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: AddDeviceRequest) => addSNMPDevice(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['snmp', 'devices'] });
    },
  });
}

export function useTestSNMPConnection() {
  return useMutation({
    mutationFn: (deviceId: number) => testSNMPConnection(deviceId),
  });
}

export function useDiscoverDevice() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (deviceId: number) => discoverDevice(deviceId),
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ queryKey: snmpKeys.device(variables) });
      queryClient.invalidateQueries({ queryKey: ['snmp', 'devices'] });
    },
  });
}

// Prefetch helpers for navigation
export function usePrefetchDeviceDetails() {
  const queryClient = useQueryClient();
  return (deviceId: number) => {
    queryClient.prefetchQuery({
      queryKey: snmpKeys.device(deviceId),
      queryFn: () => getSNMPDeviceDetails(deviceId),
      staleTime: 60000,
    });
  };
}

export function usePrefetchMonitoringConfigs() {
  const queryClient = useQueryClient();
  return (deviceId: number) => {
    queryClient.prefetchQuery({
      queryKey: snmpKeys.monitoringConfigs(deviceId),
      queryFn: () => getSNMPDeviceMonitoringConfigs(deviceId),
      staleTime: 30000,
    });
  };
}

// Invalidate all SNMP queries for a device (after config changes)
export function useInvalidateDeviceQueries() {
  const queryClient = useQueryClient();
  return (deviceId: number) => {
    queryClient.invalidateQueries({ queryKey: ['snmp', 'device', deviceId] });
    queryClient.invalidateQueries({ queryKey: ['snmp', 'monitoring', deviceId] });
    queryClient.invalidateQueries({ queryKey: ['snmp', 'metrics', 'latest', deviceId] });
    queryClient.invalidateQueries({ queryKey: ['snmp', 'metrics', 'cpu', deviceId] });
    queryClient.invalidateQueries({ queryKey: ['snmp', 'metrics', 'memory', deviceId] });
    queryClient.invalidateQueries({ queryKey: ['snmp', 'metrics', 'interfaces', deviceId] });
    queryClient.invalidateQueries({ queryKey: ['snmp', 'metrics', 'storage', deviceId] });
    queryClient.invalidateQueries({ queryKey: ['snmp', 'metrics', 'environment', deviceId] });
  };
}
