import { useTheme } from './ThemeContext'

type Alert = { id: number; type: string; msg: string; time: string }
type Props = { alerts: Alert[]; onClose: () => void; onViewAll?: () => void }

const typeStyle: Record<string, { color: string; bg: string; label: string }> = {
  critical: { color: '#ff3366', bg: 'rgba(255,51,102,0.1)', label: 'CRITICAL' },
  warning: { color: '#ffaa00', bg: 'rgba(255,170,0,0.1)', label: 'WARNING' },
  info: { color: '#00d4ff', bg: 'rgba(0,212,255,0.1)', label: 'INFO' },
}

export default function NotificationPanel({ alerts, onClose, onViewAll }: Props) {
  const { theme } = useTheme()
  const isDark = theme === 'dark'

  return (
    <div className={`absolute right-0 top-0 h-full z-50 flex flex-col ${isDark ? 'glass' : 'glass-light'}`}
      style={{ width: 340, borderLeft: '1px solid var(--t-border-alpha)', borderTop: 'none', borderRight: 'none', borderBottom: 'none' }}>
      <div className="flex items-center justify-between px-5 py-4 shrink-0"
        style={{ borderBottom: '1px solid var(--t-border-light)' }}>
        <div>
          <div className="font-display font-bold text-base tracking-widest neon-cyan">ALERTS</div>
          <div className="font-mono text-xs mt-0.5" style={{ color: 'var(--t-muted)' }}>Real-time notifications</div>
        </div>
        <button onClick={onClose} className="transition-colors" style={{ color: 'var(--t-muted)' }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {alerts.length === 0 && <div className="font-mono text-xs text-center py-8" style={{ color: 'var(--t-muted)' }}>No active alerts</div>}
        {alerts.map(a => {
          const s = typeStyle[a.type] ?? typeStyle.info
          return (
            <div key={a.id} className="rounded-lg p-3 cursor-pointer transition-all hover:scale-[1.01]"
              style={{ background: s.bg, border: `1px solid ${s.color}33` }}>
              <div className="flex items-center justify-between mb-1">
                <span className="font-mono text-xs font-semibold" style={{ color: s.color }}>{s.label}</span>
                <span className="font-mono text-xs" style={{ color: 'var(--t-muted)' }}>{a.time} ago</span>
              </div>
              <p className="text-sm leading-snug" style={{ color: 'var(--t-text)' }}>{a.msg}</p>
            </div>
          )
        })}
      </div>

      <div className="px-4 py-3 shrink-0" style={{ borderTop: '1px solid var(--t-border-light)' }}>
        <button onClick={onViewAll} className="w-full font-mono text-xs py-2 rounded transition-all neon-cyan"
          style={{ background: 'var(--t-accent-alpha)', border: '1px solid var(--t-accent-border)' }}>
          VIEW ALL ALERTS →
        </button>
      </div>
    </div>
  )
}
