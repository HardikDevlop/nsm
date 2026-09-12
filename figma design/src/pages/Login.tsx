import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'
import { useAuth } from '../components/AuthContext'
import { useBranding } from '../components/BrandingContext'
import defaultLogo from '../../header-logo.png'

export default function Login() {
  const { login } = useAuth()
  const branding = useBranding()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(email, password)
      navigate('/', { replace: true })
    } catch (err: any) {
      setError(err?.message ?? 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4" style={{ background: 'var(--t-bg, #000)' }}>
      {/* Background grid */}
      <div className="fixed inset-0 grid-bg opacity-40 pointer-events-none" />

      <div className="relative z-10 w-full max-w-sm">
        {/* Logo area */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-100 rounded-2xl flex items-center justify-center mb-4">
            <img
              src={branding.logo_url || defaultLogo}
              alt={branding.application_name}
              className="max-w-200 max-h-10 w-auto h-auto object-contain"
              onError={event => {
                // A missing/invalid runtime branding URL must not leave the
                // login mark blank when the bundled logo is available.
                if (event.currentTarget.src !== defaultLogo) event.currentTarget.src = defaultLogo
              }}
            />
          </div>
          <div className="font-display font-bold text-xl mb-2" style={{ color: 'var(--t-text)' }}>{}</div>
          <p className="font-mono text-xs tracking-widest" style={{ color: 'var(--t-muted)' }}>
            NETWORK MANAGEMENT SYSTEM
          </p>
        </div>

        {/* Login card */}
        <div className="glass rounded-xl p-6">
          <h2 className="font-display font-semibold text-lg mb-1" style={{ color: 'var(--t-text)' }}>
            Sign In
          </h2>
          <p className="font-mono text-xs mb-5" style={{ color: 'var(--t-muted)' }}>
            Enter your credentials to continue
          </p>

          {error && (
            <div className="mb-4 px-3 py-2 rounded-lg font-mono text-xs flex items-center gap-2"
              style={{ background: 'rgba(255,51,102,0.1)', border: '1px solid rgba(255,51,102,0.3)', color: '#ff3366' }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <path d="M12 8v4m0 4h.01" />
              </svg>
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="font-mono text-xs block mb-1.5" style={{ color: 'var(--t-muted)' }}>
                EMAIL
              </label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
                autoComplete="email"
                placeholder="ad****@agnigate.com"
                className="w-full rounded-lg px-3 py-2.5 font-mono text-sm outline-none transition-all"
                style={{
                  background: 'var(--t-border-light, rgba(255,255,255,0.04))',
                  border: '1px solid var(--t-border-alpha)',
                  color: 'var(--t-text)',
                }}
                onFocus={e => { e.currentTarget.style.borderColor = 'var(--t-accent)' }}
                onBlur={e => { e.currentTarget.style.borderColor = 'var(--t-border-alpha)' }}
              />
            </div>

            <div>
              <label className="font-mono text-xs block mb-1.5" style={{ color: 'var(--t-muted)' }}>
                PASSWORD
              </label>
              <input
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                autoComplete="current-password"
                placeholder="••••••••"
                className="w-full rounded-lg px-3 py-2.5 font-mono text-sm outline-none transition-all"
                style={{
                  background: 'var(--t-border-light, rgba(255,255,255,0.04))',
                  border: '1px solid var(--t-border-alpha)',
                  color: 'var(--t-text)',
                }}
                onFocus={e => { e.currentTarget.style.borderColor = 'var(--t-accent)' }}
                onBlur={e => { e.currentTarget.style.borderColor = 'var(--t-border-alpha)' }}
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-lg py-2.5 font-display font-semibold text-sm tracking-wide transition-all disabled:opacity-50"
              style={{
                background: 'var(--t-accent)',
                color: '#fff',
                border: '1px solid var(--t-accent-border)',
              }}
            >
              {loading ? 'AUTHENTICATING...' : 'SIGN IN'}
            </button>
          </form>
        </div>

        <p className="text-center font-mono text-xs mt-6" style={{ color: 'var(--t-muted)' }}>
          Agnigate NMS v4.2.1 &middot; Secure Access
        </p>
      </div>
    </div>
  )
}
