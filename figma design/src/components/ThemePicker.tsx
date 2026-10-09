import { useTheme, type ThemeColors } from './ThemeContext'

type Props = { open: boolean; onClose: () => void }

const FONT_OPTIONS = ['Josefin Sans', 'Inter', 'Roboto', 'Open Sans', 'Lato', 'Montserrat', 'Poppins', 'Nunito', 'Raleway', 'Ubuntu', 'Source Sans 3', 'DM Sans', 'Manrope', 'Outfit', 'Quicksand', 'Merriweather Sans', 'Playfair Display', 'Space Grotesk', 'Rubik', 'Work Sans']

const LABELS: Record<keyof ThemeColors, string> = {
  bg: 'Background',
  text: 'Text',
  accent: 'Accent',
  card: 'Card / Panel',
  muted: 'Muted Text',
  border: 'Border',
}

const SHADES: Record<keyof ThemeColors, string[]> = {
  bg: ['#000000', '#0a0a0a', '#111111', '#1a1a1a', '#030d1e', '#0d1117', '#f0f2f5', '#ffffff', '#fafafa', '#f5f5f0'],
  text: ['#ffffff', '#e2e8f5', '#c8d8ee', '#a0aec0', '#888888', '#666666', '#1a1a2e', '#2d3748', '#333333', '#000000'],
  accent: ['#FF0015', '#d72323', '#ff3366', '#e53e3e', '#dc2626', '#ff4500', '#00d4ff', '#00ff88', '#7c3aed', '#3b82f6'],
  card: ['#000000', '#0f0f0f', '#1a1a1a', '#1e1e2e', '#0d1117', '#ffffff', '#f8f9fa', '#f0f2f5', '#e8e8e8', '#fafafa'],
  muted: ['#ffffff', '#c8d8ee', '#a0aec0', '#888888', '#666666', '#556677', '#444444', '#333333', '#222222', '#000000'],
  border: ['#000000', '#111111', '#1e1e1e', '#2d2d2d', '#3d3d3d', '#e0e0e0', '#d0d0d0', '#c0c0c0', '#b0b0b0', '#ffffff'],
}

function ColorRow({ label, value, onChange, shades }: {
  label: string; value: string; onChange: (v: string) => void; shades: string[]
}) {
  return (
    <div className="mb-4">
      <div className="flex items-center justify-between mb-1.5">
        <span className="font-display font-semibold text-xs tracking-wider" style={{ color: 'var(--t-muted)' }}>{label}</span>
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs uppercase" style={{ color: 'var(--t-muted)' }}>{value}</span>
          <div className="relative w-7 h-7 rounded overflow-hidden" style={{ border: '2px solid var(--t-border)' }}>
            <input
              type="color"
              value={value}
              onInput={e => onChange(e.currentTarget.value)}
              onChange={e => onChange(e.currentTarget.value)}
              className="absolute inset-0 w-10 h-10 -top-1 -left-1 cursor-pointer border-none bg-transparent"
              style={{ padding: 0 }}
            />
          </div>
        </div>
      </div>
      <div className="flex gap-1.5 flex-wrap">
        {shades.map(s => (
          <button
            type="button"
            key={s}
            onClick={() => onChange(s)}
            className="w-6 h-6 rounded-sm transition-transform hover:scale-110"
            style={{
              background: s,
              border: s.toLowerCase() === value.toLowerCase()
                ? '2px solid var(--t-accent)'
                : '1px solid var(--t-border)',
              boxShadow: s.toLowerCase() === value.toLowerCase() ? '0 0 6px var(--t-accent-alpha)' : 'none',
            }}
          />
        ))}
      </div>
    </div>
  )
}

export default function ThemePicker({ open, onClose }: Props) {
  const { colors, setColor, resetColors, defaults, fontScale, setFontScale, fontFamily, setFontFamily } = useTheme()

  if (!open) return null

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 z-40" onClick={onClose} style={{ background: 'rgba(0,0,0,0.4)' }} />

      {/* Panel */}
      <div className="fixed right-0 top-0 h-full z-50 flex flex-col"
        style={{
          width: 320,
          background: 'var(--t-card-alpha)',
          backdropFilter: 'blur(20px)',
          WebkitBackdropFilter: 'blur(20px)',
          borderLeft: '1px solid var(--t-border-alpha)',
        }}>

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 shrink-0"
          style={{ borderBottom: '1px solid var(--t-border-light)' }}>
          <div>
            <div className="font-display font-bold text-base tracking-widest" style={{ color: 'var(--t-accent)' }}>
              THEME PICKER
            </div>
            <div className="font-mono text-xs mt-0.5" style={{ color: 'var(--t-muted)' }}>Customize colors</div>
          </div>
          <button onClick={onClose} className="transition-colors" style={{ color: 'var(--t-muted)' }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Color controls */}
        <div className="flex-1 overflow-y-auto p-5">
          <div className="mb-5">
            <div className="mb-5">
              <div className="mb-1.5 flex items-center justify-between">
                <span className="font-display font-semibold text-xs tracking-wider" style={{ color: 'var(--t-muted)' }}>Font Style</span>
                <span className="font-mono text-[10px]" style={{ color: 'var(--t-accent)' }}>{fontFamily}</span>
              </div>
              <select value={fontFamily} onChange={event => setFontFamily(event.target.value)} className="w-full rounded px-3 py-2 font-display text-sm" style={{ background: 'var(--t-bg)', color: 'var(--t-text)', border: '1px solid var(--t-border-alpha)' }}>
                {FONT_OPTIONS.map(font => <option key={font} value={font} style={{ fontFamily: `'${font}', sans-serif` }}>{font}</option>)}
              </select>
            </div>
            <div className="mb-1.5 flex items-center justify-between">
              <span className="font-display font-semibold text-xs tracking-wider" style={{ color: 'var(--t-muted)' }}>Font Size</span>
              <span className="font-mono text-xs" style={{ color: 'var(--t-muted)' }}>{Math.round(fontScale * 100)}%</span>
            </div>
            <div className="grid grid-cols-3 gap-2">
              {[
                { label: 'Small', value: 0.9 },
                { label: 'Medium', value: 1 },
                { label: 'Large', value: 1.1 },
              ].map(option => (
                <button
                  key={option.label}
                  onClick={() => setFontScale(option.value)}
                  className="rounded py-2 font-display text-xs transition-all"
                  style={{
                    color: fontScale === option.value ? 'var(--t-accent)' : 'var(--t-muted)',
                    background: fontScale === option.value ? 'var(--t-accent-alpha)' : 'transparent',
                    border: `1px solid ${fontScale === option.value ? 'var(--t-accent-border)' : 'var(--t-border-alpha)'}`,
                  }}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <div className="mt-3 rounded-lg border p-3" style={{ borderColor: 'var(--t-border-alpha)', background: 'var(--t-bg)' }}>
              <div className="mb-2 flex items-center justify-between font-mono text-[10px]" style={{ color: 'var(--t-muted)' }}>
                <span>Custom size</span>
                <span style={{ color: 'var(--t-accent)' }}>{Math.round(fontScale * 100)}%</span>
              </div>
              <input
                type="range"
                min="50"
                max="170"
                step="1"
                value={Math.round(fontScale * 100)}
                onChange={event => setFontScale(Number(event.target.value) / 100)}
                className="w-full accent-[var(--t-accent)]"
                aria-label="Custom font size"
              />
              <div className="mt-1 flex justify-between font-mono text-[9px]" style={{ color: 'var(--t-muted)' }}>
                <span>50%</span><span>170%</span>
              </div>
            </div>
          </div>
          {(Object.keys(LABELS) as (keyof ThemeColors)[]).map(key => (
            <ColorRow
              key={key}
              label={LABELS[key]}
              value={colors[key]}
              onChange={v => setColor(key, v)}
              shades={SHADES[key]}
            />
          ))}
        </div>

        {/* Footer */}
        <div className="px-5 py-4 shrink-0" style={{ borderTop: '1px solid var(--t-border-light)' }}>
          <button
            onClick={resetColors}
            className="w-full font-mono text-xs py-2.5 rounded transition-all"
            style={{
              color: 'var(--t-accent)',
              background: 'var(--t-accent-alpha)',
              border: '1px solid var(--t-accent-border)',
            }}
          >
            RESET TO DEFAULT
          </button>
          <div className="grid grid-cols-2 gap-x-3 gap-y-2 mt-3 min-w-0">
            {(Object.keys(defaults) as (keyof ThemeColors)[]).map(key => (
              <div key={key} className="flex min-w-0 items-center gap-1">
                <div className="w-3 h-3 rounded-full" style={{ background: defaults[key], border: '1px solid var(--t-border)' }} />
                <span className="min-w-0 truncate font-mono text-xs" style={{ color: 'var(--t-muted)', fontSize: 9 }}>{defaults[key]}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  )
}
