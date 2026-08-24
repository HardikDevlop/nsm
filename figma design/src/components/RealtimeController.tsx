import { useState, useEffect, useCallback } from 'react'

interface RealtimeControllerProps {
  onIntervalChange: (seconds: number) => void
  onTimeWindowChange: (seconds: number) => void
  currentInterval: number
  currentTimeWindow: number
  isEnabled?: boolean
  onEnabledChange?: (enabled: boolean) => void
}

const REFRESH_INTERVALS = [
  { value: 2, label: '2s' },
  { value: 5, label: '5s' }, 
  { value: 10, label: '10s' },
  { value: 15, label: '15s' },
  { value: 30, label: '30s' },
  { value: 60, label: '1m' }
]

const TIME_WINDOWS = [
  { value: 5, label: 'Last 5s', color: '#ff3366' },
  { value: 10, label: 'Last 10s', color: '#ffaa00' },
  { value: 15, label: 'Last 15s', color: '#00d4ff' },
  { value: 20, label: 'Last 20s', color: '#7c3aed' },
  { value: 25, label: 'Last 25s', color: '#00ff88' },
  { value: 30, label: 'Last 30s', color: '#ff6b9d' },
  { value: 60, label: 'Last 1m', color: '#ffd700' },
  { value: 120, label: 'Last 2m', color: '#ff8c42' },
  { value: 300, label: 'Last 5m', color: '#6c5ce7' }
]

export default function RealtimeController({
  onIntervalChange,
  onTimeWindowChange, 
  currentInterval,
  currentTimeWindow,
  isEnabled = true,
  onEnabledChange
}: RealtimeControllerProps) {
  const [isRealtime, setIsRealtime] = useState(isEnabled)
  const [showControls, setShowControls] = useState(false)

  // Handle enable/disable toggle
  const toggleRealtime = () => {
    const newState = !isRealtime
    setIsRealtime(newState)
    onEnabledChange?.(newState)
  }

  return (
    <div className="relative">
      {/* Compact Control Button */}
      <button 
        onClick={() => setShowControls(!showControls)}
        className="glass-bright rounded-lg px-4 py-2 flex items-center gap-3 hover:bg-cyan-400/5 transition-all"
        style={{ border: '1px solid rgba(0,212,255,0.3)' }}>
        
        {/* Live Status Indicator */}
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${isRealtime ? 'animate-pulse' : ''}`} 
               style={{ background: isRealtime ? '#00ff88' : '#ff3366' }}/>
          <span className="font-display font-bold text-xs tracking-wider neon-cyan">
            REAL-TIME
          </span>
        </div>

        {/* Quick Stats */}
        <div className="font-mono text-[10px]" style={{ color: 'var(--t-muted, #8899bb)' }}>
          {currentInterval}s • {currentTimeWindow}s window
        </div>

        {/* Toggle Icon */}
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#00d4ff" strokeWidth="2"
             className={`transition-transform ${showControls ? 'rotate-180' : ''}`}>
          <path d="M6 9l6 6 6-6"/>
        </svg>
      </button>

      {/* Expandable Controls Panel */}
      {showControls && (
        <>
          {/* Backdrop overlay */}
          <div 
            className="fixed inset-0 z-40" 
            onClick={() => setShowControls(false)}
          />
          
          <div className="absolute top-full right-0 mt-2 w-80 glass-bright rounded-lg p-4 space-y-4 z-50" 
               style={{ 
                 border: '1px solid rgba(0,212,255,0.3)', 
                 background: 'rgba(8,25,55,0.95)',
                 backdropFilter: 'blur(20px)',
                 boxShadow: '0 8px 32px rgba(0,0,0,0.4)'
               }}>
            
            {/* Header with Live/Pause Toggle */}
            <div className="flex items-center justify-between">
              <div className="font-display font-bold text-sm tracking-wider neon-cyan">
                CONTROL PANEL
              </div>
              <button 
                onClick={toggleRealtime}
                className={`font-mono text-xs px-3 py-1.5 rounded transition-all ${
                  isRealtime 
                    ? 'bg-green-500/20 text-green-400 border border-green-500/40' 
                    : 'bg-red-500/20 text-red-400 border border-red-500/40'
                }`}>
                {isRealtime ? '⚡ LIVE' : '⏸️ PAUSED'}
              </button>
            </div>

            {/* Refresh Interval */}
            <div>
              <div className="font-mono text-xs mb-2 flex items-center gap-2" style={{ color: 'var(--t-muted, #8899bb)' }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M23 4v6h-6M1 20v-6h6"/>
                  <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
                </svg>
                REFRESH INTERVAL
              </div>
              <div className="grid grid-cols-6 gap-1.5">
                {REFRESH_INTERVALS.map(interval => (
                  <button
                    key={interval.value}
                    onClick={() => isRealtime && onIntervalChange(interval.value)}
                    disabled={!isRealtime}
                    className={`font-mono text-xs py-1.5 rounded transition-all ${
                      currentInterval === interval.value
                        ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/40'
                        : 'bg-gray-700/20 text-gray-400 border border-gray-600/40 hover:border-cyan-500/20'
                    }`}
                    style={{ opacity: isRealtime ? 1 : 0.5 }}>
                    {interval.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Time Window */}
            <div>
              <div className="font-mono text-xs mb-2 flex items-center gap-2" style={{ color: 'var(--t-muted, #8899bb)' }}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="10"/>
                  <polyline points="12,6 12,12 16,14"/>
                </svg>
                DATA TIME WINDOW
              </div>
              <div className="grid grid-cols-4 gap-1.5">
                {TIME_WINDOWS.map(window => (
                  <button
                    key={window.value}
                    onClick={() => onTimeWindowChange(window.value)}
                    className={`font-mono text-xs py-1.5 rounded transition-all ${
                      currentTimeWindow === window.value
                        ? 'text-white border'
                        : 'text-gray-400 border border-gray-600/40 hover:border-opacity-60'
                    }`}
                    style={{
                      background: currentTimeWindow === window.value 
                        ? `${window.color}15` 
                        : 'rgba(55,65,81,0.2)',
                      borderColor: currentTimeWindow === window.value 
                        ? `${window.color}50` 
                        : undefined,
                      color: currentTimeWindow === window.value ? window.color : undefined
                    }}>
                    {window.label.replace('Last ', '')}
                  </button>
                ))}
              </div>
            </div>

            {/* Status Footer */}
            <div className="pt-2 border-t border-gray-600/20">
              <div className={`font-mono text-xs text-center py-1 rounded ${
                isRealtime 
                  ? 'text-green-400 bg-green-500/10' 
                  : 'text-red-400 bg-red-500/10'
              }`}>
                {isRealtime 
                  ? `⚡ Live Updates • Every ${currentInterval}s • ${currentTimeWindow}s History`
                  : '⏸️ Paused • Click LIVE to Resume Real-time Updates'
                }
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}