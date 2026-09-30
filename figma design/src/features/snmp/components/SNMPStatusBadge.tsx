interface SNMPStatusBadgeProps {
  status: 'supported' | 'unsupported' | 'up' | 'down' | 'unknown' | 'active' | 'inactive' | 'ok' | 'warning' | 'critical' | 'error' | 'healthy' | 'verified' | 'running' | 'stopped' | 'waiting_first_poll' | 'not_supported'
  label?: string
  size?: 'xs' | 'sm' | 'md'
}

const statusConfig = {
  supported: { color: '#00ff88', bg: 'rgba(0,255,136,0.15)', border: 'rgba(0,255,136,0.4)', text: 'Supported' },
  unsupported: { color: '#8899bb', bg: 'rgba(136,153,187,0.12)', border: 'rgba(136,153,187,0.3)', text: 'Not Supported' },
  up: { color: '#00ff88', bg: 'rgba(0,255,136,0.15)', border: 'rgba(0,255,136,0.4)', text: 'UP' },
  down: { color: '#ff3366', bg: 'rgba(255,51,102,0.15)', border: 'rgba(255,51,102,0.4)', text: 'DOWN' },
  unknown: { color: '#8899bb', bg: 'rgba(136,153,187,0.12)', border: 'rgba(136,153,187,0.3)', text: 'Unknown' },
  active: { color: '#00d4ff', bg: 'rgba(0,212,255,0.15)', border: 'rgba(0,212,255,0.4)', text: 'Active' },
  inactive: { color: '#667799', bg: 'rgba(102,119,153,0.12)', border: 'rgba(102,119,153,0.3)', text: 'Inactive' },
  ok: { color: '#00ff88', bg: 'rgba(0,255,136,0.15)', border: 'rgba(0,255,136,0.4)', text: 'OK' },
  warning: { color: '#ffaa00', bg: 'rgba(255,170,0,0.15)', border: 'rgba(255,170,0,0.4)', text: 'Warning' },
  critical: { color: '#ff3366', bg: 'rgba(255,51,102,0.15)', border: 'rgba(255,51,102,0.4)', text: 'Critical' },
  error: { color: '#ff3366', bg: 'rgba(255,51,102,0.15)', border: 'rgba(255,51,102,0.4)', text: 'Error' },
  healthy: { color: '#00ff88', bg: 'rgba(0,255,136,0.15)', border: 'rgba(0,255,136,0.4)', text: 'Healthy' },
  verified: { color: '#00ff88', bg: 'rgba(0,255,136,0.15)', border: 'rgba(0,255,136,0.4)', text: 'Verified' },
  running: { color: '#00ff88', bg: 'rgba(0,255,136,0.15)', border: 'rgba(0,255,136,0.4)', text: 'Running' },
  stopped: { color: '#ff3366', bg: 'rgba(255,51,102,0.15)', border: 'rgba(255,51,102,0.4)', text: 'Stopped' },
  waiting_first_poll: { color: '#ffaa00', bg: 'rgba(255,170,0,0.15)', border: 'rgba(255,170,0,0.4)', text: 'Waiting' },
  not_supported: { color: '#8899bb', bg: 'rgba(136,153,187,0.12)', border: 'rgba(136,153,187,0.3)', text: 'Not Supported' },
}

const sizeClasses = {
  xs: 'text-[9px] px-1.5 py-0.5',
  sm: 'text-[10px] px-2 py-0.5',
  md: 'text-xs px-2.5 py-1',
}

export default function SNMPStatusBadge({ status, label, size = 'sm' }: SNMPStatusBadgeProps) {
  const config = statusConfig[status as keyof typeof statusConfig] || statusConfig.unknown
  const displayText = label || config.text

  return (
    <span
      className={`snmp-status-badge font-mono ${sizeClasses[size]} rounded uppercase font-semibold inline-block`}
      style={{
        color: config.color,
        background: config.bg,
        border: `1px solid ${config.border}`,
      }}
    >
      {displayText}
    </span>
  )
}
