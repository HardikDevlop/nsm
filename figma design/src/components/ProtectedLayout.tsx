import { Navigate, Outlet, useLocation } from 'react-router'
import { useAuth } from './AuthContext'

/**
 * Route-level permission guard wrapper.
 * Usage in routes.ts: Component: withPermission(Dashboard, 'dashboard:read')
 */
export function withPermission(Component: React.ComponentType, permission: string) {
  return function Guarded() {
    const { hasPermission, loading } = useAuth()
    if (loading) return <LoadingSpinner />
    if (!hasPermission(permission)) return <NoAccess />
    return <Component />
  }
}

function LoadingSpinner() {
  return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--t-bg)' }}>
      <div className="flex flex-col items-center gap-3">
        <div className="w-8 h-8 rounded-full border-2 border-t-transparent animate-spin"
          style={{ borderColor: 'var(--t-accent)', borderTopColor: 'transparent' }} />
        <span className="font-mono text-xs" style={{ color: 'var(--t-muted)' }}>LOADING...</span>
      </div>
    </div>
  )
}

function NoAccess() {
  return (
    <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--t-bg)' }}>
      <div className="text-center">
        <div className="mx-auto w-16 h-16 rounded-2xl flex items-center justify-center mb-4"
          style={{ background: 'rgba(255,51,102,0.1)', border: '1px solid rgba(255,51,102,0.3)' }}>
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="#ff3366" strokeWidth="1.5">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            <path d="M12 8v4m0 4h.01" />
          </svg>
        </div>
        <h2 className="font-display font-semibold text-lg mb-1" style={{ color: 'var(--t-text)' }}>Access Denied</h2>
        <p className="font-mono text-xs" style={{ color: 'var(--t-muted)' }}>You lack permission for this resource</p>
      </div>
    </div>
  )
}

/**
 * Layout wrapper that checks authentication.
 * Redirects to /login if not authenticated.
 */
export default function ProtectedLayout() {
  const { user, loading } = useAuth()
  const location = useLocation()

  if (loading) {
    return <LoadingSpinner />
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return <Outlet />
}
