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
  const isSuperAdmin = user?.role_name === 'Admin'

  const hasPermission = useCallback(
    (code: string) => isSuperAdmin || permissions.has(code),
    [isSuperAdmin, permissions],
  )

  const hasAnyPermission = useCallback(
    (...codes: string[]) => isSuperAdmin || codes.some(c => permissions.has(c)),
    [isSuperAdmin, permissions],
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
