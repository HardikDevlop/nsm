import { forwardRef, type ReactNode, type CSSProperties, type KeyboardEvent } from 'react'

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

const GlassCard = forwardRef<HTMLDivElement, Props>(function GlassCard({
  children, className = '', style, glow, onClick, role, tabIndex, onKeyDown,
}, ref) {
  return (
    <div
      ref={ref}
      onClick={onClick}
      role={role}
      tabIndex={tabIndex}
      onKeyDown={onKeyDown}
      className={`glass rounded-xl ${onClick ? 'cursor-pointer transition-colors hover:border-[var(--t-text-secondary)]' : ''} ${className}`}
      style={style}
    >
      {children}
    </div>
  )
})

export default GlassCard
