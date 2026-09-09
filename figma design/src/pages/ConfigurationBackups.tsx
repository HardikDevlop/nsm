import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import GlassCard from '../components/GlassCard'
import { useAuth } from '../components/AuthContext'
import {
  captureConfiguration,
  compareBaselineCurrent,
  compareConfigurationVersions,
  listConfigurationVersions,
  type ConfigurationComparison,
  type ConfigurationVersion,
} from '../lib/api'

const style = { background: 'var(--t-card)', color: 'var(--t-text)', border: '1px solid var(--t-border-alpha)' }

function DiffView({ diff }: { diff: ConfigurationComparison }) {
  return <div className="grid gap-3 md:grid-cols-3 p-4">
    <div><h3 className="font-display font-semibold text-sm" style={{ color: '#4ade80' }}>Added lines</h3>{diff.added_lines.map((line, index) => <pre key={index} className="mt-1 font-mono text-xs whitespace-pre-wrap" style={{ color: '#4ade80' }}>+ {line}</pre>)}</div>
    <div><h3 className="font-display font-semibold text-sm" style={{ color: '#ff6688' }}>Removed lines</h3>{diff.removed_lines.map((line, index) => <pre key={index} className="mt-1 font-mono text-xs whitespace-pre-wrap" style={{ color: '#ff6688' }}>- {line}</pre>)}</div>
    <div><h3 className="font-display font-semibold text-sm" style={{ color: '#ffb86b' }}>Changed lines</h3>{diff.changed_lines.map((change, index) => <pre key={index} className="mt-1 font-mono text-xs whitespace-pre-wrap" style={{ color: '#ffb86b' }}>v{change.from_number}: {change.from_line.join('\n')}\nv{change.to_number}: {change.to_line.join('\n')}</pre>)}</div>
    <div className="md:col-span-3 font-mono text-[10px]" style={{ color: 'var(--t-muted)' }}>Comparison initiated by user {diff.initiated_by ?? 'unknown'} at {new Date(diff.created_at).toLocaleString()}</div>
  </div>
}

export default function ConfigurationBackups() {
  const { hasPermission } = useAuth(); const client = useQueryClient()
  const [deviceId, setDeviceId] = useState<number>(); const [content, setContent] = useState(''); const [source, setSource] = useState('manual'); const [fromVersion, setFromVersion] = useState<number>(); const [toVersion, setToVersion] = useState<number>()
  const versions = useQuery({ queryKey: ['configuration-versions', deviceId], queryFn: () => listConfigurationVersions(deviceId!), enabled: hasPermission('config_backups:read') && deviceId != null, staleTime: 30_000, refetchOnWindowFocus: false, refetchOnMount: false })
  const comparison = useQuery({ queryKey: ['configuration-comparison', deviceId, fromVersion, toVersion], queryFn: () => compareConfigurationVersions(deviceId!, fromVersion!, toVersion!), enabled: deviceId != null && fromVersion != null && toVersion != null && fromVersion !== toVersion, staleTime: 30_000, refetchOnWindowFocus: false })
  const baseline = useQuery({ queryKey: ['configuration-baseline-current', deviceId], queryFn: () => compareBaselineCurrent(deviceId!), enabled: false, staleTime: 30_000, refetchOnWindowFocus: false })
  const capture = useMutation({ mutationFn: () => captureConfiguration({ device_id: deviceId!, source, content }), onSuccess: () => { setContent(''); client.invalidateQueries({ queryKey: ['configuration-versions', deviceId] }) } })
  if (!hasPermission('config_backups:read')) return <div className="p-6 font-mono text-sm" style={{ color: 'var(--t-muted)' }}>You do not have permission to view configuration backups.</div>
  if (versions.isLoading) return <div className="p-6 font-mono text-sm" style={{ color: 'var(--t-accent)' }}>Loading configuration history...</div>
  if (versions.error) return <div className="p-6 font-mono text-sm" style={{ color: '#ff6b8a' }}>Unable to load configuration history: {versions.error instanceof Error ? versions.error.message : 'Request failed'}</div>
  const rows: ConfigurationVersion[] = versions.data?.items ?? []; const diff = comparison.data ?? baseline.data
  return <div className="p-4 md:p-6 space-y-5">
    <div><h1 className="font-display font-bold text-2xl tracking-widest" style={{ color: 'var(--t-text)' }}>CONFIGURATION BACKUPS</h1><p className="font-mono text-xs mt-1" style={{ color: 'var(--t-muted)' }}>Encrypted device configuration versions with checksum deduplication</p></div>
    <GlassCard><div className="flex flex-wrap gap-2 p-4"><input aria-label="Device ID" type="number" min="1" value={deviceId ?? ''} onChange={event => { setDeviceId(event.target.value ? Number(event.target.value) : undefined); setFromVersion(undefined); setToVersion(undefined) }} placeholder="Device ID" className="w-32 rounded px-3 py-2 font-mono text-xs" style={style} /><select aria-label="Configuration source" value={source} onChange={event => setSource(event.target.value)} className="rounded px-3 py-2 font-mono text-xs" style={style}><option value="manual">Manual</option><option value="scheduled">Scheduled</option><option value="startup">Startup</option><option value="discovery">Discovery</option></select><textarea aria-label="Configuration content" value={content} onChange={event => setContent(event.target.value)} placeholder="Paste live captured configuration" className="min-w-[280px] flex-1 rounded px-3 py-2 font-mono text-xs" style={style} />{hasPermission('config_backups:execute') && <button type="button" onClick={() => capture.mutate()} disabled={!deviceId || !content.trim()} className="rounded px-3 py-2 font-mono text-xs" style={{ background: '#00d4ff', color: '#06111a' }}>Capture configuration</button>}</div></GlassCard>
    <GlassCard className="overflow-hidden"><div className="px-4 py-3 font-display font-semibold text-sm" style={{ borderBottom: '1px solid var(--t-border-light)' }}>Configuration history</div><div className="overflow-x-auto"><table className="w-full text-left"><thead><tr style={{ color: 'var(--t-muted)' }}>{['Version', 'Source', 'Checksum', 'Captured', 'Startup'].map(label => <th key={label} className="px-4 py-2 font-mono text-[10px] uppercase">{label}</th>)}</tr></thead><tbody>{rows.map(row => <tr key={row.id} style={{ borderTop: '1px solid var(--t-border-alpha)' }}><td className="px-4 py-2 font-mono text-xs">v{row.version}</td><td className="px-4 py-2 font-mono text-xs">{row.source}</td><td className="px-4 py-2 font-mono text-[10px]">{row.checksum}</td><td className="px-4 py-2 font-mono text-xs">{new Date(row.captured_at).toLocaleString()}</td><td className="px-4 py-2 font-mono text-xs">{row.is_startup ? 'yes' : 'no'}</td></tr>)}</tbody></table>{!rows.length && <div className="p-8 text-center font-mono text-xs" style={{ color: 'var(--t-muted)' }}>Enter a device ID to inspect configuration history.</div>}</div></GlassCard>
    {rows.length > 1 && <GlassCard><div className="px-4 py-3 font-display font-semibold text-sm">Compare configuration versions</div><div className="flex flex-wrap gap-2 p-4"><select aria-label="From version" value={fromVersion ?? ''} onChange={event => setFromVersion(event.target.value ? Number(event.target.value) : undefined)} className="rounded px-3 py-2 font-mono text-xs" style={style}><option value="">From version</option>{rows.map(row => <option key={row.version} value={row.version}>v{row.version}</option>)}</select><select aria-label="To version" value={toVersion ?? ''} onChange={event => setToVersion(event.target.value ? Number(event.target.value) : undefined)} className="rounded px-3 py-2 font-mono text-xs" style={style}><option value="">To version</option>{rows.map(row => <option key={row.version} value={row.version}>v{row.version}</option>)}</select><button type="button" onClick={() => baseline.refetch()} className="rounded px-3 py-2 font-mono text-xs" style={{ background: 'var(--t-border-alpha)', color: 'var(--t-text)' }}>Compare baseline/current</button></div>{diff && <DiffView diff={diff} />}</GlassCard>}
  </div>
}
