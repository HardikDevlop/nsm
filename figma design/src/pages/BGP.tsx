import { useQuery } from '@tanstack/react-query'
import GlassCard from '../components/GlassCard'
import { useAuth } from '../components/AuthContext'
import { listBGPNeighbors } from '../lib/api'

export default function BGP() {
  const { hasPermission } = useAuth()
  const q = useQuery({ queryKey: ['bgp-neighbors'], queryFn: () => listBGPNeighbors(), enabled: hasPermission('bgp:read'), staleTime: 30000, refetchOnWindowFocus: false })
  if (!hasPermission('bgp:read')) return <div className="p-6">Unauthorized</div>
  return <div className="p-4 md:p-6">
    <h1 className="font-display font-bold text-2xl tracking-widest">BGP MONITORING</h1>
    <GlassCard className="mt-5 overflow-x-auto">
      {q.isLoading && <div className="p-6 text-center font-mono text-xs" style={{ color: 'var(--t-accent)' }}>Loading BGP data...</div>}
      {q.error && <div className="p-6 text-center font-mono text-xs" style={{ color: '#ff6b8a' }}>Unable to load BGP data: {q.error instanceof Error ? q.error.message : 'Request failed'}</div>}
      {!q.isLoading && !q.error && !q.data?.length && <div className="p-6 text-center font-mono text-xs" style={{ color: 'var(--t-muted)' }}>No BGP neighbor data available.</div>}
      {!!q.data?.length && <table className="w-full text-left font-mono text-xs"><thead><tr>{['Device','Neighbor','State','AS','Next hop','Prefixes','AS path'].map(x => <th className="p-3" key={x}>{x}</th>)}</tr></thead><tbody>{q.data.map(x => <tr key={x.id}><td className="p-3">{x.device_id}</td><td className="p-3">{x.neighbor}</td><td className="p-3">{x.state}</td><td className="p-3">{x.remote_as ?? '-'}</td><td className="p-3">{x.next_hop ?? '-'}</td><td className="p-3">{x.prefixes}</td><td className="p-3">{x.as_path ?? '-'}</td></tr>)}</tbody></table>}
    </GlassCard>
  </div>
}
