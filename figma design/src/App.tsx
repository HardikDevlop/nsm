import { ThemeProvider } from './components/ThemeContext'
import { AuthProvider } from './components/AuthContext'
import { RouterProvider } from 'react-router'
import { router } from './routes.tsx'
import { QueryProvider } from './lib/queryProvider'

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <QueryProvider>
          <RouterProvider router={router} />
        </QueryProvider>
      </AuthProvider>
    </ThemeProvider>
  )
}
