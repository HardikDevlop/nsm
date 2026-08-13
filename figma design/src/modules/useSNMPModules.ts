import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { requestJson } from '../lib/api';
import { SNMPModuleConfig, getModuleConfig, MODULE_ORDER } from './snmpModuleRegistry';

// Types for module data
export interface SNMPModuleData {
  [key: string]: any;
}

export interface SNMPMonitoringConfig {
  module_name: string;
  enabled: boolean;
  interval_seconds: number;
  status: string;
  last_started_at: string | null;
  last_stopped_at: string | null;
  last_poll_at: string | null;
  next_poll_at: string | null;
  error_message: string | null;
}

export interface SNMPDeviceCapabilities {
  [key: string]: boolean;
}

// NEW: Fetch monitoring data using our working API
export async function fetchMonitoringData(deviceId: number): Promise<any> {
  return requestJson<any>('/monitoring/data', {
    method: 'POST',
    body: JSON.stringify({
      device_id: deviceId,
      modules: ["system", "cpu", "memory", "storage", "interfaces", "environment", "vlan", "lldp", "cdp", "routing", "arp", "mac_table", "firewall", "wireless", "inventory", "topology", "health"],
      include_history: false,
      history_hours: 1
    }),
  });
}

// NEW: Hook to use monitoring data API
export function useMonitoringData(deviceId: number | null) {
  return useQuery<any>({
    queryKey: ['monitoring', 'data', deviceId],
    queryFn: () => fetchMonitoringData(deviceId!),
    enabled: !!deviceId,
    staleTime: 5000,
    refetchInterval: 15000,
    refetchIntervalInBackground: true,
    retry: 1,
  });
}

export async function fetchLiveSNMPPoll(deviceId: number): Promise<any> {
  return requestJson<any>(`/snmp/devices/${deviceId}/poll`, {
    method: 'POST',
  });
}

export function useLiveSNMPPoll(deviceId: number | null) {
  return useQuery<any>({
    queryKey: ['snmp', 'live-poll', deviceId],
    queryFn: () => fetchLiveSNMPPoll(deviceId!),
    enabled: !!deviceId,
    staleTime: 5000,
    refetchInterval: 30000,
    refetchIntervalInBackground: true,
    retry: 1,
  });
}
export const moduleKeys = {
  deviceCapabilities: (deviceId: number) => ['snmp', 'capabilities', deviceId] as const,
  moduleData: (deviceId: number, moduleId: string) => ['snmp', 'module', moduleId, deviceId] as const,
  monitoringConfigs: (deviceId: number) => ['snmp', 'monitoring', deviceId] as const,
  monitoringStatus: (deviceId: number, module: string) => ['snmp', 'monitoring', deviceId, module] as const,
  allModulesData: (deviceId: number) => ['snmp', 'modules', 'all', deviceId] as const,
};

// Fetch device capabilities
export async function fetchDeviceCapabilities(deviceId: number): Promise<SNMPDeviceCapabilities> {
  return requestJson<SNMPDeviceCapabilities>(`/snmp/devices/${deviceId}/capabilities`);
}

// Fetch single module data
export async function fetchModuleData(deviceId: number, moduleId: string): Promise<SNMPModuleData> {
  const moduleConfig = getModuleConfig(moduleId);
  if (!moduleConfig) {
    throw new Error(`Unknown module: ${moduleId}`);
  }
  const endpoint = moduleConfig.apiEndpoint.replace('{deviceId}', String(deviceId));
  return requestJson<SNMPModuleData>(endpoint);
}

// Fetch all module data for a device (overview)
export async function fetchAllModulesData(deviceId: number): Promise<Record<string, SNMPModuleData>> {
  const overview = await requestJson<any>(`/snmp/devices/${deviceId}/overview`);
  return overview.modules || {};
}

// Fetch monitoring configs
export async function fetchMonitoringConfigs(deviceId: number): Promise<SNMPMonitoringConfig[]> {
  return requestJson<SNMPMonitoringConfig[]>(`/snmp/devices/${deviceId}/monitoring`);
}

// Start module monitoring
export async function startModuleMonitoringApi(
  deviceId: number,
  module: string,
  intervalSeconds: number
): Promise<SNMPMonitoringConfig & { message: string }> {
  return requestJson(`/snmp/devices/${deviceId}/monitoring/${module}/start`, {
    method: 'POST',
    body: JSON.stringify({ module_name: module, interval_seconds: intervalSeconds }),
  });
}

// Stop module monitoring
export async function stopModuleMonitoringApi(
  deviceId: number,
  module: string
): Promise<{ stopped: boolean; message: string }> {
  return requestJson(`/snmp/devices/${deviceId}/monitoring/${module}/stop`, {
    method: 'POST',
  });
}

// Update module monitoring
export async function updateModuleMonitoringApi(
  deviceId: number,
  module: string,
  data: { enabled?: boolean; interval_seconds?: number }
): Promise<SNMPMonitoringConfig> {
  return requestJson(`/snmp/devices/${deviceId}/monitoring/${module}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

// Get module monitoring status
export async function getModuleMonitoringStatusApi(
  deviceId: number,
  module: string
): Promise<SNMPMonitoringConfig> {
  return requestJson<SNMPMonitoringConfig>(`/snmp/devices/${deviceId}/monitoring/${module}/status`);
}

// Hooks
export function useDeviceCapabilities(deviceId: number | null) {
  return useQuery<SNMPDeviceCapabilities>({
    queryKey: moduleKeys.deviceCapabilities(deviceId!),
    queryFn: () => fetchDeviceCapabilities(deviceId!),
    enabled: !!deviceId,
    staleTime: 60000, // 1 minute
  });
}

export function useModuleData(deviceId: number | null, moduleId: string | null) {
  return useQuery<SNMPModuleData>({
    queryKey: moduleKeys.moduleData(deviceId!, moduleId!),
    queryFn: () => fetchModuleData(deviceId!, moduleId!),
    enabled: !!deviceId && !!moduleId,
    staleTime: 5000,
    refetchInterval: 15000,
    refetchIntervalInBackground: true,
  });
}

export function useAllModulesData(deviceId: number | null) {
  return useQuery<Record<string, SNMPModuleData>>({
    queryKey: moduleKeys.allModulesData(deviceId!),
    queryFn: () => fetchAllModulesData(deviceId!),
    enabled: !!deviceId,
    staleTime: 30000,
  });
}

export function useMonitoringConfigs(deviceId: number | null) {
  return useQuery<SNMPMonitoringConfig[]>({
    queryKey: moduleKeys.monitoringConfigs(deviceId!),
    queryFn: () => fetchMonitoringConfigs(deviceId!),
    enabled: !!deviceId,
    staleTime: 30000,
  });
}

export function useModuleMonitoringStatus(deviceId: number | null, module: string | null) {
  return useQuery<SNMPMonitoringConfig>({
    queryKey: moduleKeys.monitoringStatus(deviceId!, module!),
    queryFn: () => getModuleMonitoringStatusApi(deviceId!, module!),
    enabled: !!deviceId && !!module,
    staleTime: 10000, // 10 seconds
  });
}

// Mutations
export function useStartModuleMonitoring() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ deviceId, module, intervalSeconds }: { deviceId: number; module: string; intervalSeconds: number }) =>
      startModuleMonitoringApi(deviceId, module, intervalSeconds),
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ queryKey: moduleKeys.monitoringConfigs(variables.deviceId) });
      queryClient.invalidateQueries({ queryKey: moduleKeys.monitoringStatus(variables.deviceId, variables.module) });
    },
  });
}

export function useStopModuleMonitoring() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ deviceId, module }: { deviceId: number; module: string }) =>
      stopModuleMonitoringApi(deviceId, module),
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ queryKey: moduleKeys.monitoringConfigs(variables.deviceId) });
      queryClient.invalidateQueries({ queryKey: moduleKeys.monitoringStatus(variables.deviceId, variables.module) });
    },
  });
}

export function useUpdateModuleMonitoring() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ deviceId, module, data }: { deviceId: number; module: string; data: { enabled?: boolean; interval_seconds?: number } }) =>
      updateModuleMonitoringApi(deviceId, module, data),
    onSuccess: (data, variables) => {
      queryClient.invalidateQueries({ queryKey: moduleKeys.monitoringConfigs(variables.deviceId) });
      queryClient.invalidateQueries({ queryKey: moduleKeys.monitoringStatus(variables.deviceId, variables.module) });
    },
  });
}

// Helper hook to get monitoring config for a specific module
export function useModuleMonitoringConfig(deviceId: number | null, moduleId: string | null, allConfigs: SNMPMonitoringConfig[] | undefined) {
  if (!deviceId || !moduleId || !allConfigs) return null;
  return allConfigs.find(c => c.module_name === moduleId) || null;
}
