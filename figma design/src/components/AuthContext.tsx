import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react'
import { getMe, login as apiLogin, logout as apiLogout, type UserRecord } from '../lib/api'

interface AuthContextType {
  user: UserRecord | null
  permissions: Set<string>
  isSuperAdmin: boolean
  hasPermission: (code: string) => boolean
  hasAnyPermission: (...codes: string[]) => boolean
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  loading: boolean
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  permissions: new Set(),
  isSuperAdmin: false,
  hasPermission: () => false,
  hasAnyPermission: () => false,
  login: async () => {},
  logout: () => {},
  loading: true,
})

const USER_CACHE_KEY = 'nms.user.cache.v1'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserRecord | null>(null)
  const [loading, setLoading] = useState(true)

  const permissions = new Set(user?.permissions ?? [])
  // A role name must never grant implicit access. Permissions are the source
  // of truth; this flag is kept for backwards compatibility with consumers.
  const isSuperAdmin = false

  const hasPermission = useCallback(
    (code: string) => permissions.has(code),
    [permissions],
  )

  const hasAnyPermission = useCallback(
    (...codes: string[]) => codes.some(c => permissions.has(c)),
    [permissions],
  )

  const hydrateUser = useCallback(async (ignoreMissingToken = false, forceRefresh = true) => {
    const token = window.localStorage.getItem('nms_access_token')
    if (!token) {
      if (!ignoreMissingToken) setLoading(false)
      return null
    }
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
    } catch {
      try {
        const cached = JSON.parse(window.sessionStorage.getItem(USER_CACHE_KEY) || 'null') as UserRecord | null
        if (cached) {
          setUser(cached)
          return cached
        }
      } catch {
        // fall through to clear auth
      }
      window.localStorage.removeItem('nms_access_token')
      window.sessionStorage.removeItem(USER_CACHE_KEY)
      setUser(null)
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  // On mount: if token exists in localStorage, fetch user in the background.
  useEffect(() => {
    let ignore = false
    void (async () => {
      const token = window.localStorage.getItem('nms_access_token')
      if (!token) {
        setLoading(false)
        return
      }
      if (ignore) return
      await hydrateUser(true, false)
    })()
    return () => { ignore = true }
  }, [hydrateUser])

  const login = useCallback(async (email: string, password: string) => {
    await apiLogin(email, password)
    setLoading(false)
    void hydrateUser(true, false)
  }, [hydrateUser])

  const logout = useCallback(() => {
    apiLogout()
    setUser(null)
    try {
      window.sessionStorage.removeItem(USER_CACHE_KEY)
    } catch {
      // ignore storage failures
    }
    setLoading(false)
  }, [])

  return (
    <AuthContext.Provider value={{ user, permissions, isSuperAdmin, hasPermission, hasAnyPermission, login, logout, loading }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
