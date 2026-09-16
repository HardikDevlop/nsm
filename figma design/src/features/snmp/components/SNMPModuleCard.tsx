import { ReactNode } from 'react'
import { useNavigate } from 'react-router'
import GlassCard from '../../../components/GlassCard'

interface SNMPModuleCardProps {
  title: string
  icon: string
  status: 'supported' | 'unsupported' | 'error' | 'loading'
  health?: 'healthy' | 'warning' | 'critical' | 'unknown'
  lastPoll?: string | null
  objectCount?: number
  summary?: ReactNode
  navigateTo?: string
  onClick?: () => void
  className?: string
}

const healthColors = {
  healthy: { color: '#00ff88', bg: 'rgba(0,255,136,0.12)', border: 'rgba(0,255,136,0.3)' },
  warning: { color: '#ffaa00', bg: 'rgba(255,170,0,0.12)', border: 'rgba(255,170,0,0.3)' },
  critical: { color: '#ff3366', bg: 'rgba(255,51,102,0.12)', border: 'rgba(255,51,102,0.3)' },
  unknown: { color: '#8899bb', bg: 'rgba(136,153,187,0.12)', border: 'rgba(136,153,187,0.3)' },
}

const statusColors = {
  supported: { color: '#00d4ff', text: 'Supported' },
  unsupported: { color: '#8899bb', text: 'Not Supported' },
  error: { color: '#ff3366', text: 'Error' },
  loading: { color: '#7c3aed', text: 'Loading...' },
}

export default function SNMPModuleCard({
  title,
  icon,
  status,
  health = 'unknown',
  lastPoll,
  objectCount,
  summary,
  navigateTo,
  onClick,
  className = '',
}: SNMPModuleCardProps) {
  const navigate = useNavigate()
  const healthStyle = healthColors[health]
  const statusStyle = statusColors[status]
  const isInteractive = navigateTo || onClick

  const handleClick = () => {
    if (onClick) {
      onClick()
    } else if (navigateTo) {
      navigate(navigateTo)
    }
  }

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      handleClick()
    }
  }

  return (
    <GlassCard
      className={`p-4 transition-all ${isInteractive ? 'cursor-pointer hover:bg-cyan-400/5' : ''} ${className}`}
      onClick={isInteractive ? handleClick : undefined}
      role={isInteractive ? 'button' : undefined}
      tabIndex={isInteractive ? 0 : undefined}
      onKeyDown={isInteractive ? handleKeyDown : undefined}
    >
      <div className="flex items-start gap-3">
        {/* Icon */}
        <div
          className="w-10 h-10 rounded-lg flex items-center justify-center shrink-0"
          style={{ background: 'rgba(0,212,255,0.08)', border: '1px solid rgba(0,212,255,0.2)' }}
        >
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="#00d4ff"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d={icon} />
          </svg>
        </div>

        <div className="flex-1 min-w-0">
          {/* Header */}
          <div className="flex items-start justify-between gap-2 mb-2">
            <div className="flex-1 min-w-0">
              <h3 className="font-display font-bold text-sm tracking-wider neon-cyan truncate">
                {title}
              </h3>
            </div>
            {/* Health Indicator */}
            {status === 'supported' && (
              <div
                className="w-2 h-2 rounded-full shrink-0 mt-1"
                style={{ background: healthStyle.color, boxShadow: `0 0 8px ${healthStyle.color}` }}
                title={`Health: ${health}`}
              />
            )}
          </div>

          {/* Status Badge */}
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <span
              className="font-mono text-[10px] px-2 py-0.5 rounded uppercase font-semibold"
              style={{
                color: statusStyle.color,
                background: `${statusStyle.color}15`,
                border: `1px solid ${statusStyle.color}40`,
              }}
            >
              {statusStyle.text}
            </span>
            {objectCount !== undefined && status === 'supported' && (
              <span className="font-mono text-[10px]" style={{ color: '#8899bb' }}>
                {objectCount} object{objectCount !== 1 ? 's' : ''}
              </span>
            )}
          </div>

          {/* Summary Content */}
          {status === 'supported' && summary && (
            <div className="mb-2">{summary}</div>
          )}

          {/* Unsupported Message */}
          {status === 'unsupported' && (
            <div className="font-mono text-xs mb-2" style={{ color: '#667799' }}>
              No Data Available From Device
            </div>
          )}

          {/* Error Message */}
          {status === 'error' && (
            <div className="font-mono text-xs mb-2" style={{ color: '#ff3366' }}>
              Failed to retrieve data
            </div>
          )}

          {/* Footer */}
          <div className="flex items-center justify-between gap-2 mt-2 pt-2" style={{ borderTop: '1px solid rgba(0,212,255,0.06)' }}>
            <span className="font-mono text-[10px]" style={{ color: '#667799' }}>
              {lastPoll ? `Updated ${formatTimestamp(lastPoll)}` : 'Not polled'}
            </span>
            {isInteractive && status === 'supported' && (
              <span className="font-mono text-[10px] flex items-center gap-1" style={{ color: '#00d4ff' }}>
                View
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M5 12h14M12 5l7 7-7 7" />
                </svg>
              </span>
            )}
          </div>
        </div>
      </div>
    </GlassCard>
  )
}

function formatTimestamp(timestamp: string): string {
  try {
    const date = new Date(timestamp)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffSec = Math.floor(diffMs / 1000)
    const diffMin = Math.floor(diffSec / 60)
    const diffHr = Math.floor(diffMin / 60)
    const diffDays = Math.floor(diffHr / 24)

    if (diffSec < 60) return `${diffSec}s ago`
    if (diffMin < 60) return `${diffMin}m ago`
    if (diffHr < 24) return `${diffHr}h ago`
    if (diffDays < 7) return `${diffDays}d ago`
    return date.toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata' })
  } catch {
    return 'recently'
  }
}
