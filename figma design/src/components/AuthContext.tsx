import { createContext, useContext, useState, useEffect, useCallback, useMemo, useRef, type ReactNode } from 'react'
import { getMe, login as apiLogin, serverLogout, logout as apiLogout, type UserRecord } from '../lib/api'

interface AuthContextType {
  user: UserRecord | null
  permissions: Set<string>
  authorityLevel: number
  isSuperAdmin: boolean
  canManageAuthority: (targetLevel: number | null | undefined) => boolean
  hasPermission: (code: string) => boolean
  hasAnyPermission: (...codes: string[]) => boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  loading: boolean
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  permissions: new Set(),
  authorityLevel: 0,
  isSuperAdmin: false,
  canManageAuthority: () => false,
  hasPermission: () => false,
  hasAnyPermission: () => false,
  login: async () => {},
  logout: () => {},
  loading: true,
})

const USER_CACHE_KEY = 'nms.user.cache.v2'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserRecord | null>(null)
  const [loading, setLoading] = useState(true)
  const initializationRef = useRef<Promise<UserRecord | null> | null>(null)

  const permissions = useMemo(() => new Set(user?.permissions ?? []), [user?.permissions])
  // Hierarchy is UX-only; the backend remains the security source of truth.
  // Missing or malformed authority must never grant elevated access.
  const authorityLevel = typeof user?.authority_level === 'number' && Number.isFinite(user.authority_level)
    ? user.authority_level
    : 0
  const isSuperAdmin = authorityLevel === 100
  const canManageAuthority = useCallback(
    (targetLevel: number | null | undefined) => (
      authorityLevel > 0 && typeof targetLevel === 'number' && Number.isFinite(targetLevel) &&
      authorityLevel > targetLevel
    ),
    [authorityLevel],
  )

  const hasPermission = useCallback(
    (code: string) => permissions.has(code),
    [permissions],
  )

  const hasAnyPermission = useCallback(
    (...codes: string[]) => codes.some(c => permissions.has(c)),
    [permissions],
  )

  const hydrateUser = useCallback(async (ignoreMissingToken = false, forceRefresh = true) => {
    // React StrictMode intentionally mounts effects twice in development. Keep
    // auth initialization single-flight so that behavior does not create two
    // /auth/me requests (and so concurrent callers share the same validation).
    if (initializationRef.current && forceRefresh) return initializationRef.current
    const token = window.localStorage.getItem('nms_access_token')
    if (!token) {
      if (!ignoreMissingToken) setLoading(false)
      return null
    }
    setLoading(true)
    const request = (async () => {
    try {
      const cached = JSON.parse(window.sessionStorage.getItem(USER_CACHE_KEY) || 'null') as UserRecord | null
      if (cached) {
        setUser(cached)
        setLoading(false)
        if (!forceRefresh) return cached
      }
    } catch {
      // Ignore malformed cache and fall back to a network check.
    }
    try {
      const u = await getMe()
      setUser(u)
      try {
        window.sessionStorage.setItem(USER_CACHE_KEY, JSON.stringify(u))
      } catch {
        // optional cache only
      }
      return u
    } catch (error) {
      window.localStorage.removeItem('nms_access_token')
      window.sessionStorage.removeItem(USER_CACHE_KEY)
      setUser(null)
      // A forced refresh is the source of truth. Never authenticate with a
      // stale cached user when the current token cannot be validated.
      if (forceRefresh) throw error
      return null
    } finally {
      setLoading(false)
    }
    })()
    if (forceRefresh) {
      initializationRef.current = request
      void request.then(() => undefined, () => undefined).finally(() => {
        if (initializationRef.current === request) initializationRef.current = null
      })
    }
    return request
  }, [])

  useEffect(() => {
    const token = window.localStorage.getItem('nms_access_token')
    if (!token) return
    const timer = window.setInterval(() => {
      void hydrateUser(true, true).catch(() => undefined)
    }, 30000)
    return () => window.clearInterval(timer)
  }, [hydrateUser])

  // On mount: hydrate from cache immediately, then refresh from API so RBAC
  // changes like newly-seeded permissions show up without manual storage clear.
  useEffect(() => {
    let ignore = false
    void (async () => {
      const token = window.localStorage.getItem('nms_access_token')
      if (!token) {
        setLoading(false)
        return
      }
      if (ignore) return
      await hydrateUser(true, true).catch(() => undefined)
    })()
    return () => { ignore = true }
  }, [hydrateUser])

  const login = useCallback(async (email: string, password: string) => {
    await apiLogin(email, password)
    // Load the user and permissions before protected routes render. Navigating
    // with only a token set creates a race where the guard sends us back to login.
    const currentUser = await hydrateUser(true, true)
    if (!currentUser) throw new Error('Unable to load your account. Please try again.')
  }, [hydrateUser])

  const logout = useCallback(() => {
    // Clear the browser session immediately. The server revoke request is
    // best-effort and must never leave the application stuck on a spinner.
    void serverLogout().catch(() => undefined)
    apiLogout()
    initializationRef.current = null
    setUser(null)
    try {
      window.sessionStorage.removeItem(USER_CACHE_KEY)
    } catch {
      // ignore storage failures
    }
    setLoading(false)
  }, [])

  const contextValue = useMemo(() => ({ user, permissions, authorityLevel, isSuperAdmin, canManageAuthority, hasPermission, hasAnyPermission, login, logout, loading }), [user, permissions, authorityLevel, isSuperAdmin, canManageAuthority, hasPermission, hasAnyPermission, login, logout, loading])

  return (
    <AuthContext.Provider value={contextValue}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
