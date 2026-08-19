interface SNMPHealthIndicatorProps {
  health: 'healthy' | 'warning' | 'critical' | 'unknown'
  size?: 'sm' | 'md' | 'lg'
  showLabel?: boolean
  className?: string
}

const healthConfig = {
  healthy: { color: '#00ff88', label: 'Healthy' },
  warning: { color: '#ffaa00', label: 'Warning' },
  critical: { color: '#ff3366', label: 'Critical' },
  unknown: { color: '#8899bb', label: 'Unknown' },
}

const sizeMap = {
  sm: { dot: 'w-2 h-2', text: 'text-[10px]' },
  md: { dot: 'w-3 h-3', text: 'text-xs' },
  lg: { dot: 'w-4 h-4', text: 'text-sm' },
}

export default function SNMPHealthIndicator({
  health,
  size = 'md',
  showLabel = false,
  className = '',
}: SNMPHealthIndicatorProps) {
  const config = healthConfig[health]
  const sizes = sizeMap[size]

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <div
        className={`${sizes.dot} rounded-full shrink-0`}
        style={{
          background: config.color,
          boxShadow: `0 0 8px ${config.color}`,
        }}
        title={`Health: ${config.label}`}
      />
      {showLabel && (
        <span className={`font-mono ${sizes.text} font-semibold`} style={{ color: config.color }}>
          {config.label}
        </span>
      )}
    </div>
  )
}
