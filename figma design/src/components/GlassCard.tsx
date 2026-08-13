import type { ReactNode, CSSProperties, KeyboardEvent } from 'react'

type Props = {
  children: ReactNode
  className?: string
  style?: CSSProperties
  glow?: 'cyan' | 'green' | 'red' | 'amber'
  onClick?: () => void
  role?: string
  tabIndex?: number
  onKeyDown?: (e: KeyboardEvent<HTMLDivElement>) => void
}

const glowMap = {
  cyan:  'glow-border-cyan',
  green: 'glow-border-green',
  red:   'glow-border-red',
  amber: 'glow-border-amber',
}

export default function GlassCard({
  children, className = '', style, glow, onClick, role, tabIndex, onKeyDown,
}: Props) {
  return (
    <div
      onClick={onClick}
      role={role}
      tabIndex={tabIndex}
      onKeyDown={onKeyDown}
      className={`glass rounded-xl ${glow ? glowMap[glow] : ''} ${onClick ? 'cursor-pointer hover:border-cyan-400/30 transition-all' : ''} ${className}`}
      style={style}
    >
      {children}
    </div>
  )
}
