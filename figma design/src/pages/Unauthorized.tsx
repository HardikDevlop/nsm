import { useNavigate } from 'react-router'

export default function Unauthorized() {
  const navigate = useNavigate()

  return (
    <div className="min-h-screen flex items-center justify-center px-4" style={{ background: 'var(--t-bg, #000)' }}>
      <div className="fixed inset-0 grid-bg opacity-30 pointer-events-none" />

      <div className="relative z-10 text-center max-w-md">
        {/* Shield icon */}
        <div className="mx-auto w-20 h-20 rounded-2xl flex items-center justify-center mb-6"
          style={{ background: 'rgba(255,51,102,0.1)', border: '1px solid rgba(255,51,102,0.3)' }}>
          <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#ff3366" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            <path d="M12 8v4m0 4h.01" />
          </svg>
        </div>

        <h1 className="font-display font-bold text-4xl mb-2" style={{ color: '#ff3366' }}>
          403
        </h1>
        <h2 className="font-display font-semibold text-xl mb-2" style={{ color: 'var(--t-text)' }}>
          Access Denied
        </h2>
        <p className="font-mono text-sm mb-6" style={{ color: 'var(--t-muted)' }}>
          You don't have permission to access this resource. Contact your administrator if you believe this is an error.
        </p>

        <div className="flex gap-3 justify-center">
          <button
            onClick={() => navigate(-1)}
            className="rounded-lg px-5 py-2.5 font-display font-medium text-sm transition-all"
            style={{
              background: 'rgba(255,255,255,0.05)',
              border: '1px solid var(--t-border-alpha)',
              color: 'var(--t-text)',
            }}
          >
            Go Back
          </button>
          <button
            onClick={() => navigate('/')}
            className="rounded-lg px-5 py-2.5 font-display font-medium text-sm transition-all"
            style={{
              background: 'var(--t-accent)',
              border: '1px solid var(--t-accent-border)',
              color: '#fff',
            }}
          >
            Dashboard
          </button>
        </div>
      </div>
    </div>
  )
}
