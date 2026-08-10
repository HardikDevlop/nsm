import { type ReactNode } from 'react'
import { useAuth } from './AuthContext'

/** Renders children only if the user has the specified permission. */
export function PermissionGuard({ permission, children, fallback }: {
  permission: string
  children: ReactNode
  fallback?: ReactNode
}) {
  const { hasPermission } = useAuth()
  if (!hasPermission(permission)) return fallback ? <>{fallback}</> : null
  return <>{children}</>
}

/** Wraps an entire page — redirects to fallback if user lacks permission. */
export function RequirePermission({ permission, children, fallback }: {
  permission: string
  children: ReactNode
  fallback?: ReactNode
}) {
  const { hasPermission } = useAuth()
  if (!hasPermission(permission)) {
    return fallback ? <>{fallback}</> : null
  }
  return <>{children}</>
}
