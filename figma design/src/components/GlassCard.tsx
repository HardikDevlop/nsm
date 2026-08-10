import type { ReactNode, CSSProperties } from 'react'

type Props = {
  children: ReactNode
  className?: string
  style?: CSSProperties
  glow?: 'cyan' | 'green' | 'red' | 'amber'
  onClick?: () => void
}

const glowMap = {
  cyan: 'glow-border-cyan',
  green: 'glow-border-green',
  red: 'glow-border-red',
  amber: 'glow-border-amber',
}

export default function GlassCard({ children, className = '', style, glow, onClick }: Props) {
  return (
    <div
      onClick={onClick}
      className={`glass rounded-xl ${glow ? glowMap[glow] : ''} ${onClick ? 'cursor-pointer hover:border-cyan-400/30 transition-all' : ''} ${className}`}
      style={style}
    >
      {children}
    </div>
  )
}
