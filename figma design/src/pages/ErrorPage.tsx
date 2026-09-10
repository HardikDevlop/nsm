import { useRouteError, isRouteErrorResponse, Link, useRevalidator } from 'react-router'
import { isModuleLoadError } from '../components/moduleLoadError'
import GlassCard from '../components/GlassCard'

export default function ErrorPage() {
  const error = useRouteError()
  const revalidator = useRevalidator()
  
  let errorMessage: string
  let errorStatus: string | number = 'Error'

  if (isRouteErrorResponse(error)) {
    errorMessage = error.data?.message || error.statusText || 'Something went wrong'
    errorStatus = error.status
  } else if (error instanceof Error) {
    errorMessage = error.message
  } else if (typeof error === 'string') {
    errorMessage = error
  } else {
    errorMessage = 'Unknown error occurred'
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4" style={{ background: 'linear-gradient(135deg, #0a0f1c 0%, #1a2332 100%)' }}>
      <GlassCard className="p-8 max-w-md w-full text-center">
        <div className="mb-6">
          <h1 className="font-display font-bold text-3xl mb-2 neon-cyan">
            {errorStatus}
          </h1>
          <h2 className="font-display font-bold text-xl mb-4" style={{ color: '#ff6644' }}>
            Oops! Something went wrong
          </h2>
          <p className="font-mono text-sm mb-6" style={{ color: 'var(--t-muted, #8899bb)' }}>
            {errorMessage}
          </p>
        </div>
        
        <div className="space-y-3">
          <Link 
            to="/"
            className="block w-full px-4 py-2 rounded font-mono text-sm transition-all"
            style={{ background: 'rgba(0,212,255,0.15)', color: '#00d4ff', border: '1px solid rgba(0,212,255,0.4)' }}
          >
            ← Back to Dashboard
          </Link>
          
          <Link 
            to="/snmp-monitoring"
            className="block w-full px-4 py-2 rounded font-mono text-sm transition-all"
            style={{ background: 'rgba(0,255,136,0.15)', color: '#00ff88', border: '1px solid rgba(0,255,136,0.4)' }}
          >
            Go to SNMP Monitoring
          </Link>
          
          <button 
            onClick={() => {
              if (isModuleLoadError(error)) window.location.reload()
              else revalidator.revalidate()
            }}
            className="w-full px-4 py-2 rounded font-mono text-sm transition-all"
            style={{ background: 'rgba(255,170,0,0.15)', color: '#ffaa00', border: '1px solid rgba(255,170,0,0.4)' }}
          >
            {revalidator.state === 'loading' ? 'Refreshing…' : 'Retry Route'}
          </button>
        </div>
        
        <div className="mt-6 pt-4 border-t border-gray-600">
          <p className="font-mono text-xs" style={{ color: 'var(--t-muted, #667799)' }}>
            If this error persists, please check the URL or contact support.
          </p>
        </div>
      </GlassCard>
    </div>
  )
}
