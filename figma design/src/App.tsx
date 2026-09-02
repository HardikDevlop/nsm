import { ThemeProvider } from './components/ThemeContext'
import { AuthProvider } from './components/AuthContext'
import { RouterProvider } from 'react-router'
import { Suspense } from 'react'
import { router } from './routes.tsx'
import { QueryProvider } from './lib/queryProvider'
import { I18nProvider, useI18n } from './i18n/I18nContext'
import { BrandingProvider } from './components/BrandingContext'

function LoadingFallback() {
  const { t } = useI18n()

  return <div className="min-h-screen flex items-center justify-center font-mono text-sm" style={{ color: '#00d4ff', background: '#000' }}>{t.loading}</div>
}

export default function App() {
  return (
    <I18nProvider><BrandingProvider><ThemeProvider>
      <AuthProvider>
        <QueryProvider>
          <Suspense fallback={<LoadingFallback />}>
            <RouterProvider router={router} />
          </Suspense>
        </QueryProvider>
      </AuthProvider>
    </ThemeProvider></BrandingProvider></I18nProvider>
  )
}
