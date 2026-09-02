import { useQuery } from '@tanstack/react-query'
import GlassCard from '../components/GlassCard'
import { useAuth } from '../components/AuthContext'
import { listConfigurationCompliancePolicies, listConfigurationComplianceViolations } from '../lib/api'

export default function ConfigurationCompliance() {
  const { hasPermission } = useAuth()
  const policies = useQuery({ queryKey: ['configuration-compliance-policies'], queryFn: listConfigurationCompliancePolicies, enabled: hasPermission('config_compliance:read'), staleTime: 30_000, refetchOnWindowFocus: false })
  const violations = useQuery({ queryKey: ['configuration-compliance-violations'], queryFn: () => listConfigurationComplianceViolations('open'), enabled: hasPermission('config_compliance:read'), staleTime: 30_000, refetchOnWindowFocus: false })
  if (!hasPermission('config_compliance:read')) return <div className="p-6 font-mono text-sm">You do not have permission to view compliance.</div>
  return <div className="p-4 md:p-6 space-y-5"><h1 className="font-display font-bold text-2xl tracking-widest">CONFIGURATION COMPLIANCE</h1><GlassCard><div className="px-4 py-3 font-display font-semibold">Policies</div><div className="p-4 space-y-2">{(policies.data?.items ?? []).map(policy => <div key={policy.id} className="font-mono text-xs">{policy.name} <span style={{ color: 'var(--t-muted)' }}>{policy.enabled ? 'enabled' : 'disabled'} | {JSON.stringify(policy.rules)}</span></div>)}</div></GlassCard><GlassCard><div className="px-4 py-3 font-display font-semibold">Open violations</div><div className="p-4 space-y-3">{(violations.data?.items ?? []).map(item => <div key={item.id} className="font-mono text-xs"><strong>{item.severity.toUpperCase()}</strong> device {item.device_id}, version {item.version}: {item.recommendation}</div>)}{!violations.data?.items.length && <div className="font-mono text-xs">No open violations.</div>}</div></GlassCard></div>
}
