import { ReactNode, useMemo } from 'react';
import { useNavigate, useParams } from 'react-router';
import GlassCard from '../../../components/GlassCard';
import SNMPStatusBadge from '../components/SNMPStatusBadge';
import { useSNMPDeviceDetails, useStartModuleMonitoring, useStopModuleMonitoring, useUpdateModuleMonitoring } from '../hooks/useSnmpQueries';
import { SNMPModuleConfig, getModuleConfig, getSupportedModuleConfigs, MODULE_ORDER } from './snmpModuleRegistry';
import { useModuleMonitoringConfig } from './useSNMPModules';

const INTERVALS = [15, 30, 60, 120, 300, 600];

function title(text: string) {
  return text.replace(/_/g, ' ').replace(/\b\w/g, char => char.toUpperCase());
}

interface SNMPModuleShellProps {
  module: string;
  title?: string;
  children: ReactNode;
  unsupportedMessage?: string;
  showMonitoringControls?: boolean;
  allowUnsupportedContent?: boolean;
}

export function SNMPModuleShell({
  module,
  title: pageTitle,
  children,
  unsupportedMessage,
  showMonitoringControls = true,
  allowUnsupportedContent = false,
}: SNMPModuleShellProps) {
  const { deviceId } = useParams<{ deviceId: string }>();
  const navigate = useNavigate();
  const id = Number(deviceId);
  const { data, isLoading, error } = useSNMPDeviceDetails(id);
  const start = useStartModuleMonitoring();
  const stop = useStopModuleMonitoring();
  const update = useUpdateModuleMonitoring();

  const moduleConfig = useMemo(() => getModuleConfig(module), [module]);
  
  // Call ALL hooks before any conditional returns (Rules of Hooks)
  const monitoringConfig = useModuleMonitoringConfig(id, module, data?.monitoring);
  const supportedModules = useMemo(() => getSupportedModuleConfigs(data?.capabilities || {}), [data?.capabilities]);

  if (isLoading) {
    return (
      <div className="p-4 md:p-6 space-y-4 md:space-y-5">
        <div className="flex items-center justify-center p-12">
          <div className="font-mono text-sm" style={{ color: '#00d4ff' }}>Loading device...</div>
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-4 md:p-6">
        <GlassCard className="p-6 text-center">
          <div className="font-display font-bold" style={{ color: '#ff3366' }}>Unable to load SNMP device</div>
          <div className="font-mono text-xs mt-2" style={{ color: '#8899bb' }}>{error?.message ?? 'Device not found'}</div>
        </GlassCard>
      </div>
    );
  }

  const device = data.device;
  const capabilities = data.capabilities || {};
  const monitoringList = Array.isArray(data.monitoring) ? data.monitoring : [];
  const supported = module === 'overview' || module === 'monitoring' || Boolean(capabilities[module]);
  const safeMonitoringConfig = monitoringConfig || monitoringList.find(item => item.module_name === module) || null;
  const isRunning = safeMonitoringConfig?.status === 'running';
  const interval = safeMonitoringConfig?.interval_seconds ?? 60;
  const moduleRoutes = supportedModules.map(m => m.route).filter(Boolean);

  const handleStartMonitoring = async (intervalSeconds: number) => {
    try {
      await start.mutateAsync({ deviceId: id, module, intervalSeconds });
    } catch (err) {
      console.error('Failed to start monitoring:', err);
    }
  };

  const handleStopMonitoring = async () => {
    try {
      await stop.mutateAsync({ deviceId: id, module });
    } catch (err) {
      console.error('Failed to stop monitoring:', err);
    }
  };

  const handleUpdateInterval = async (intervalSeconds: number) => {
    try {
      await update.mutateAsync({ deviceId: id, module, data: { interval_seconds: intervalSeconds } });
    } catch (err) {
      console.error('Failed to update interval:', err);
    }
  };

  const handleToggleEnabled = async (enabled: boolean) => {
    try {
      await update.mutateAsync({ deviceId: id, module, data: { enabled } });
    } catch (err) {
      console.error('Failed to toggle monitoring:', err);
    }
  };

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-5">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 font-mono text-xs" style={{ color: '#667799' }}>
        <button type="button" onClick={() => navigate('/snmp/devices')} className="hover:text-cyan-400 transition-colors">SNMP DEVICES</button>
        <span>/</span>
        <button type="button" onClick={() => navigate(`/snmp/devices/${id}`)} className="hover:text-cyan-400 transition-colors">{device.name || device.ip_address}</button>
        <span>/</span>
        <span style={{ color: '#c8d8ee' }}>{pageTitle ?? title(module)}</span>
      </div>

      {/* Header */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
        <div className="min-w-0">
          <h1 className="font-display font-bold text-xl sm:text-2xl tracking-widest neon-cyan">{pageTitle ?? title(module)}</h1>
          <p className="font-mono text-xs mt-0.5" style={{ color: '#8899bb' }}>
            {device.name || device.hostname || device.ip_address} · {device.ip_address} · {device.last_seen ? `Last seen ${new Date(device.last_seen).toLocaleString()}` : 'Last seen N/A'}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <SNMPStatusBadge status={data.snmp.status === 'verified' ? 'verified' : 'unknown'} />
          {module !== 'overview' && module !== 'monitoring' && moduleConfig && (
            <>
              {showMonitoringControls && monitoringConfig && (
                <>
                  <select
                    value={interval}
                    disabled={!supported}
                    onChange={event => update.mutate({ deviceId: id, module, data: { interval_seconds: Number(event.target.value) } })}
                    className="glass-bright rounded px-2 py-1.5 font-mono text-xs"
                    style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.7)', opacity: supported ? 1 : 0.5 }}
                  >
                    {INTERVALS.map(value => <option key={value} value={value}>{value}s</option>)}
                  </select>
                  {isRunning ? (
                    <button type="button" disabled={!supported || stop.isPending} onClick={handleStopMonitoring}
                      className="px-3 py-1.5 rounded font-mono text-xs" style={{ border: '1px solid rgba(255,51,102,0.35)', color: '#ff3366', background: 'rgba(255,51,102,0.1)' }}>
                      STOP MONITORING
                    </button>
                  ) : (
                    <button type="button" disabled={!supported || start.isPending} onClick={() => handleStartMonitoring(interval)}
                      className="px-3 py-1.5 rounded font-mono text-xs" style={{ border: '1px solid rgba(0,255,136,0.35)', color: '#00ff88', background: 'rgba(0,255,136,0.1)' }}>
                      START MONITORING
                    </button>
                  )}
                </>
              )}
              {!showMonitoringControls && (
                <>
                  <select
                    value={interval}
                    disabled={!supported}
                    onChange={event => update.mutate({ deviceId: id, module, data: { interval_seconds: Number(event.target.value) } })}
                    className="glass-bright rounded px-2 py-1.5 font-mono text-xs"
                    style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.7)', opacity: supported ? 1 : 0.5 }}
                  >
                    {INTERVALS.map(value => <option key={value} value={value}>{value}s</option>)}
                  </select>
                  {isRunning ? (
                    <button type="button" disabled={!supported || stop.isPending} onClick={handleStopMonitoring}
                      className="px-3 py-1.5 rounded font-mono text-xs" style={{ border: '1px solid rgba(255,51,102,0.35)', color: '#ff3366', background: 'rgba(255,51,102,0.1)' }}>
                      STOP
                    </button>
                  ) : (
                    <button type="button" disabled={!supported || start.isPending} onClick={() => handleStartMonitoring(interval)}
                      className="px-3 py-1.5 rounded font-mono text-xs" style={{ border: '1px solid rgba(0,255,136,0.35)', color: '#00ff88', background: 'rgba(0,255,136,0.1)' }}>
                      START
                    </button>
                  )}
                </>
              )}
            </>
          )}
        </div>
      </div>

      {/* Module Navigation Tabs */}
      <div className="flex flex-wrap gap-1.5 pb-1">
        {MODULE_ORDER.map(key => {
          const modConfig = getModuleConfig(key);
          if (!modConfig) return null;
          const ok = key === 'overview' || key === 'monitoring' || Boolean(capabilities[key]);
          const active = key === module;
          const route = modConfig.route ? `/${modConfig.route}` : '';
          const bg = active
            ? 'rgba(0,212,255,0.15)'
            : ok
              ? 'rgba(0,255,136,0.10)'
              : 'transparent';
          const fg = active ? '#00d4ff' : ok ? '#00ff88' : '#556677';
          const border = active
            ? 'rgba(0,212,255,0.4)'
            : ok
              ? 'rgba(0,255,136,0.35)'
              : 'rgba(0,212,255,0.1)';
          return (
            <button key={key} type="button" onClick={() => navigate(`/snmp/devices/${id}${route}`)}
              className="font-mono text-[11px] sm:text-xs px-2.5 py-2 rounded"
              style={{
                background: bg,
                color: fg,
                border: `1px solid ${border}`,
                cursor: 'pointer',
              }}>
              {modConfig.label}{!ok ? ' · NS' : ''}
            </button>
          );
        })}
      </div>

      {!supported && !allowUnsupportedContent ? (
        <GlassCard className="p-8 text-center">
          <div className="font-display font-bold text-base" style={{ color: '#8899bb' }}>
            {unsupportedMessage ?? `${moduleConfig?.label ?? title(module)} is not supported by this device.`}
          </div>
        </GlassCard>
      ) : children}
    </div>
  );
}
