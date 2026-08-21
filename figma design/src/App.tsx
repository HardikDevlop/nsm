import { ThemeProvider } from './components/ThemeContext'
import { AuthProvider } from './components/AuthContext'
import { RouterProvider } from 'react-router'
import { Suspense } from 'react'
import { router } from './routes.tsx'
import { QueryProvider } from './lib/queryProvider'

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <QueryProvider>
          <Suspense fallback={<div className="min-h-screen flex items-center justify-center font-mono text-sm" style={{ color: '#00d4ff', background: '#000' }}>Loading…</div>}>
            <RouterProvider router={router} />
          </Suspense>
        </QueryProvider>
      </AuthProvider>
    </ThemeProvider>
  )
}
