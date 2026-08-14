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

  // On mount: if token exists in localStorage, fetch user
  useEffect(() => {
    let ignore = false
    const token = window.localStorage.getItem('nms_access_token')
    if (!token) {
      setLoading(false)
      return
    }
    getMe()
      .then(u => { if (!ignore) setUser(u) })
      .catch(() => {
        if (!ignore) {
          window.localStorage.removeItem('nms_access_token')
          setUser(null)
        }
      })
      .finally(() => { if (!ignore) setLoading(false) })
    return () => { ignore = true }
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    await apiLogin(email, password)
    const me = await getMe()
    setUser(me)
  }, [])

  const logout = useCallback(() => {
    apiLogout()
    setUser(null)
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
