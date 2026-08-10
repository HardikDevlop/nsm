import { useCallback, useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router'
import GlassCard from '../components/GlassCard'
import SNMPStatusBadge from '../components/SNMPStatusBadge'
import { getSNMPOIDCache, getSNMPSystemInfo, type SNMPOIDCacheEntry, type SNMPSystemInfo } from '../lib/api'

// ── Helpers ───────────────────────────────────────────────────────────────────

function parseOID(oid: string): string[] {
  return oid.split('.').filter(Boolean)
}

// Build a tree structure from flat OID list
interface OIDNode {
  oid: string
  label: string
  value?: string
  type?: string
  supported: boolean
  children: Map<string, OIDNode>
  vendorSpecific: boolean
}

function buildTree(entries: SNMPOIDCacheEntry[]): OIDNode {
  const root: OIDNode = {
    oid: '',
    label: 'root',
    supported: true,
    children: new Map(),
    vendorSpecific: false,
  }

  for (const entry of entries) {
    const parts = parseOID(entry.oid)
    let current = root

    let accumulated = ''
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i]
      accumulated = accumulated ? `${accumulated}.${part}` : part
      
      if (!current.children.has(part)) {
        const isLeaf = i === parts.length - 1
        current.children.set(part, {
          oid: accumulated,
          label: isLeaf && entry.oid_name ? entry.oid_name : part,
          value: isLeaf ? entry.value : undefined,
          type: isLeaf ? entry.type : undefined,
          supported: entry.supported,
          children: new Map(),
          vendorSpecific: entry.vendor_specific,
        })
      }
      current = current.children.get(part)!
    }
  }

  return root
}

// Well-known OID prefixes
const OID_PREFIXES: Record<string, string> = {
  '1': 'iso',
  '1.3': 'org',
  '1.3.6': 'dod',
  '1.3.6.1': 'internet',
  '1.3.6.1.2': 'mgmt',
  '1.3.6.1.2.1': 'mib-2',
  '1.3.6.1.2.1.1': 'system',
  '1.3.6.1.2.1.2': 'interfaces',
  '1.3.6.1.2.1.25': 'host-resources',
  '1.3.6.1.4': 'private',
  '1.3.6.1.4.1': 'enterprises',
}

// ── Tree Node Component ───────────────────────────────────────────────────────

function TreeNode({
  node,
  depth = 0,
  onSelect,
}: {
  node: OIDNode
  depth?: number
  onSelect: (node: OIDNode) => void
}) {
  const [expanded, setExpanded] = useState(depth < 2) // Auto-expand first 2 levels
  const hasChildren = node.children.size > 0
  const isLeaf = !hasChildren

  const wellKnown = OID_PREFIXES[node.oid]
  const displayLabel = wellKnown || node.label

  return (
    <div>
      <div
        className="flex items-center gap-2 py-1.5 px-2 rounded cursor-pointer transition-all hover:bg-cyan-400/5"
        style={{ paddingLeft: `${depth * 20 + 8}px` }}
        onClick={() => {
          if (hasChildren) setExpanded(!expanded)
          if (isLeaf) onSelect(node)
        }}
      >
        {/* Expand/collapse icon */}
        {hasChildren && (
          <svg
            width="12"
            height="12"
            viewBox="0 0 24 24"
            fill="none"
            stroke="#00d4ff"
            strokeWidth="2"
            style={{ transform: expanded ? 'rotate(90deg)' : 'rotate(0deg)', transition: 'transform 0.2s' }}
          >
            <path d="M9 18l6-6-6-6" />
          </svg>
        )}
        {!hasChildren && <div className="w-3" />}

        {/* Icon */}
        <div
          className="w-5 h-5 rounded flex items-center justify-center shrink-0"
          style={{
            background: isLeaf ? 'rgba(0,212,255,0.1)' : 'rgba(124,58,237,0.1)',
            border: `1px solid ${isLeaf ? 'rgba(0,212,255,0.2)' : 'rgba(124,58,237,0.2)'}`,
          }}
        >
          <svg
            width="10"
            height="10"
            viewBox="0 0 24 24"
            fill="none"
            stroke={isLeaf ? '#00d4ff' : '#7c3aed'}
            strokeWidth="2"
          >
            {isLeaf ? (
              <path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            ) : (
              <path d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
            )}
          </svg>
        </div>

        {/* Label */}
        <span
          className="font-mono text-xs flex-1"
          style={{
            color: wellKnown ? '#00d4ff' : isLeaf ? '#c8d8ee' : '#8899bb',
            fontWeight: wellKnown ? 600 : 400,
          }}
        >
          {displayLabel}
        </span>

        {/* OID */}
        <span className="font-mono text-[10px] shrink-0" style={{ color: '#556677' }}>
          {node.oid}
        </span>

        {/* Value preview for leaves */}
        {isLeaf && node.value && (
          <span
            className="font-mono text-[10px] px-2 py-0.5 rounded max-w-[120px] truncate"
            style={{ background: 'rgba(0,255,136,0.1)', color: '#00ff88' }}
            title={node.value}
          >
            {node.value}
          </span>
        )}

        {/* Vendor badge */}
        {node.vendorSpecific && (
          <span
            className="font-mono text-[9px] px-1.5 py-0.5 rounded"
            style={{ background: 'rgba(255,170,0,0.15)', color: '#ffaa00' }}
          >
            VENDOR
          </span>
        )}

        {/* Supported badge */}
        {isLeaf && !node.supported && (
          <SNMPStatusBadge status="unsupported" size="xs" />
        )}
      </div>

      {/* Children */}
      {expanded && hasChildren && (
        <div>
          {Array.from(node.children.values())
            .sort((a, b) => {
              const aNum = parseInt(a.label, 10)
              const bNum = parseInt(b.label, 10)
              if (!isNaN(aNum) && !isNaN(bNum)) return aNum - bNum
              return a.label.localeCompare(b.label)
            })
            .map(child => (
              <TreeNode key={child.oid} node={child} depth={depth + 1} onSelect={onSelect} />
            ))}
        </div>
      )}
    </div>
  )
}

// ── OID Detail Panel ──────────────────────────────────────────────────────────

function OIDDetail({ oid, onClose }: { oid: SNMPOIDCacheEntry; onClose: () => void }) {
  const copyOID = () => {
    navigator.clipboard.writeText(oid.oid)
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4"
      style={{ background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)' }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        className="w-full max-w-2xl rounded-xl p-6 space-y-4"
        style={{ background: 'rgba(8,25,55,0.98)', border: '1px solid rgba(0,212,255,0.2)' }}
      >
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-2">
              <h2 className="font-display font-bold text-lg neon-cyan">OID Details</h2>
              <SNMPStatusBadge status={oid.supported ? 'supported' : 'unsupported'} />
              {oid.vendor_specific && (
                <span
                  className="font-mono text-[10px] px-2 py-0.5 rounded"
                  style={{ background: 'rgba(255,170,0,0.15)', color: '#ffaa00', border: '1px solid rgba(255,170,0,0.3)' }}
                >
                  VENDOR SPECIFIC
                </span>
              )}
            </div>
            {oid.oid_name && (
              <div className="font-mono text-sm mb-1" style={{ color: '#c8d8ee' }}>{oid.oid_name}</div>
            )}
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg transition-all hover:bg-white/5"
            style={{ color: '#8899bb' }}
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M18 6L6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="space-y-3">
          <div>
            <div className="font-mono text-[10px] mb-1" style={{ color: '#667799' }}>OID</div>
            <div className="flex items-center gap-2">
              <code
                className="flex-1 font-mono text-sm px-3 py-2 rounded"
                style={{ background: 'rgba(0,0,0,0.3)', color: '#00d4ff', border: '1px solid rgba(0,212,255,0.15)' }}
              >
                {oid.oid}
              </code>
              <button
                onClick={copyOID}
                className="px-3 py-2 rounded font-mono text-xs transition-all hover:bg-cyan-400/10"
                style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#00d4ff' }}
                title="Copy OID"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M8 4v12a2 2 0 002 2h8a2 2 0 002-2V7.242a2 2 0 00-.602-1.43L16.083 2.57A2 2 0 0014.685 2H10a2 2 0 00-2 2z" />
                  <path d="M16 18v2a2 2 0 01-2 2H6a2 2 0 01-2-2V9a2 2 0 012-2h2" />
                </svg>
              </button>
            </div>
          </div>

          {oid.value && (
            <div>
              <div className="font-mono text-[10px] mb-1" style={{ color: '#667799' }}>Current Value</div>
              <div
                className="font-mono text-sm px-3 py-2 rounded"
                style={{ background: 'rgba(0,255,136,0.1)', color: '#00ff88', border: '1px solid rgba(0,255,136,0.2)' }}
              >
                {oid.value}
              </div>
            </div>
          )}

          {oid.type && (
            <div>
              <div className="font-mono text-[10px] mb-1" style={{ color: '#667799' }}>Data Type</div>
              <span
                className="font-mono text-xs px-2 py-1 rounded"
                style={{ background: 'rgba(124,58,237,0.15)', color: '#7c3aed', border: '1px solid rgba(124,58,237,0.3)' }}
              >
                {oid.type}
              </span>
            </div>
          )}

          {oid.mib && (
            <div>
              <div className="font-mono text-[10px] mb-1" style={{ color: '#667799' }}>MIB</div>
              <div className="font-mono text-xs" style={{ color: '#c8d8ee' }}>{oid.mib}</div>
            </div>
          )}

          <div>
            <div className="font-mono text-[10px] mb-1" style={{ color: '#667799' }}>Last Seen</div>
            <div className="font-mono text-xs" style={{ color: '#8899bb' }}>
              {new Date(oid.last_seen).toLocaleString()}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function SNMPOIDExplorer() {
  const { deviceId } = useParams<{ deviceId: string }>()
  const navigate = useNavigate()
  const id = Number(deviceId)

  const [entries, setEntries] = useState<SNMPOIDCacheEntry[]>([])
  const [sysInfo, setSysInfo] = useState<SNMPSystemInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [view, setView] = useState<'tree' | 'table'>('tree')
  const [selected, setSelected] = useState<SNMPOIDCacheEntry | null>(null)

  const load = useCallback(async () => {
    if (!id) return
    setLoading(true)
    setError(null)
    try {
      const [oidData, sysData] = await Promise.all([
        getSNMPOIDCache(id),
        getSNMPSystemInfo(id),
      ])
      setEntries(oidData)
      setSysInfo(sysData)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load OID data')
    } finally {
      setLoading(false)
    }
  }, [id])

  useEffect(() => { void load() }, [load])

  const tree = buildTree(entries)

  const filtered = search.trim()
    ? entries.filter(e => {
        const q = search.toLowerCase()
        return e.oid.includes(q) ||
          (e.oid_name ?? '').toLowerCase().includes(q) ||
          (e.value ?? '').toLowerCase().includes(q) ||
          (e.mib ?? '').toLowerCase().includes(q)
      })
    : entries

  const supportedCount = entries.filter(e => e.supported).length
  const vendorCount = entries.filter(e => e.vendor_specific).length

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-5">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 font-mono text-xs" style={{ color: '#667799' }}>
        <button onClick={() => navigate(`/snmp/dashboard/${id}`)} className="hover:text-cyan-400 transition-colors">
          SNMP
        </button>
        <span>/</span>
        <span style={{ color: '#c8d8ee' }}>OID Explorer</span>
      </div>

      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h1 className="font-display font-bold text-xl sm:text-2xl tracking-widest neon-cyan">
            OID EXPLORER
          </h1>
          <p className="font-mono text-xs mt-0.5" style={{ color: '#8899bb' }}>
            {sysInfo?.hostname || `Device ${id}`} · {entries.length} OID{entries.length !== 1 ? 's' : ''} cached
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {/* View Toggle */}
          <div className="flex" style={{ border: '1px solid rgba(0,212,255,0.2)', borderRadius: 6 }}>
            {(['tree', 'table'] as const).map(v => (
              <button
                key={v}
                onClick={() => setView(v)}
                className="font-mono text-xs px-3 py-1.5 transition-all capitalize"
                style={{
                  background: view === v ? 'rgba(0,212,255,0.15)' : 'transparent',
                  color: view === v ? '#00d4ff' : '#8899bb',
                  borderRight: v === 'tree' ? '1px solid rgba(0,212,255,0.15)' : 'none',
                }}
              >
                {v}
              </button>
            ))}
          </div>
          <button
            onClick={() => void load()}
            className="glass-bright px-3 py-1.5 rounded font-mono text-xs transition-all hover:bg-cyan-400/10 flex items-center gap-1.5"
            style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#00d4ff' }}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M23 4v6h-6M1 20v-6h6" />
              <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" />
            </svg>
            REFRESH
          </button>
        </div>
      </div>

      {error && (
        <div className="font-mono text-xs p-4 rounded" style={{ color: '#ff3366', background: 'rgba(255,51,102,0.1)', border: '1px solid rgba(255,51,102,0.3)' }}>
          {error}
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center p-12">
          <span className="font-mono text-sm" style={{ color: '#00d4ff' }}>Loading OID cache...</span>
        </div>
      )}

      {!loading && entries.length === 0 && (
        <GlassCard className="p-8 text-center space-y-3">
          <div className="font-display font-bold text-lg" style={{ color: '#8899bb' }}>
            No OID Cache Available
          </div>
          <div className="font-mono text-sm" style={{ color: '#667799' }}>
            No Data Available From Device
          </div>
          <button
            onClick={() => navigate(`/snmp/dashboard/${id}`)}
            className="mt-4 px-4 py-2 rounded font-mono text-xs"
            style={{ background: 'rgba(0,212,255,0.1)', color: '#00d4ff', border: '1px solid rgba(0,212,255,0.3)' }}
          >
            Back to Dashboard
          </button>
        </GlassCard>
      )}

      {!loading && entries.length > 0 && (
        <>
          {/* Stats */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {[
              { l: 'Total OIDs', v: entries.length, c: '#00d4ff' },
              { l: 'Supported', v: supportedCount, c: '#00ff88' },
              { l: 'Vendor', v: vendorCount, c: '#ffaa00' },
              { l: 'Standard', v: entries.length - vendorCount, c: '#7c3aed' },
            ].map(s => (
              <GlassCard key={s.l} className="p-4 text-center">
                <div className="font-display font-bold text-2xl" style={{ color: s.c }}>{s.v}</div>
                <div className="font-mono text-xs mt-1" style={{ color: '#8899bb' }}>{s.l}</div>
              </GlassCard>
            ))}
          </div>

          {/* Search */}
          <input
            type="text"
            placeholder="Search OIDs, names, values, MIBs..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full px-4 py-2.5 rounded font-mono text-xs"
            style={{ background: 'rgba(8,25,55,0.6)', border: '1px solid rgba(0,212,255,0.2)', color: '#c8d8ee', outline: 'none' }}
          />

          {/* Tree View */}
          {view === 'tree' && !search && (
            <GlassCard className="p-4">
              <div className="font-display font-bold text-sm tracking-wider neon-cyan mb-4">OID TREE</div>
              <div className="max-h-[600px] overflow-y-auto">
                {Array.from(tree.children.values()).map(child => (
                  <TreeNode
                    key={child.oid}
                    node={child}
                    onSelect={node => {
                      const entry = entries.find(e => e.oid === node.oid)
                      if (entry) setSelected(entry)
                    }}
                  />
                ))}
              </div>
            </GlassCard>
          )}

          {/* Table View */}
          {(view === 'table' || search) && (
            <GlassCard className="overflow-hidden">
              <div className="p-4" style={{ borderBottom: '1px solid rgba(0,212,255,0.1)' }}>
                <div className="font-display font-bold text-sm tracking-wider neon-cyan">
                  OID TABLE {search && `(${filtered.length} matches)`}
                </div>
              </div>
              <div className="max-h-[600px] overflow-y-auto overflow-x-auto">
                <table className="w-full" style={{ minWidth: 700 }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid rgba(0,212,255,0.08)' }}>
                      {['OID', 'Name', 'Value', 'Type', 'MIB', 'Status'].map(h => (
                        <th
                          key={h}
                          className="text-left px-4 py-3 font-mono text-xs sticky top-0"
                          style={{ color: '#8899bb', background: 'rgba(8,25,55,0.95)' }}
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map(oid => (
                      <tr
                        key={oid.id}
                        onClick={() => setSelected(oid)}
                        className="cursor-pointer hover:bg-cyan-400/5 transition-colors"
                        style={{ borderBottom: '1px solid rgba(0,212,255,0.04)' }}
                      >
                        <td className="px-4 py-2.5 font-mono text-xs" style={{ color: '#00d4ff' }}>
                          {oid.oid}
                          {oid.vendor_specific && (
                            <span className="ml-2 font-mono text-[9px] px-1 py-0.5 rounded"
                              style={{ background: 'rgba(255,170,0,0.15)', color: '#ffaa00' }}>
                              VENDOR
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-2.5 font-mono text-xs" style={{ color: '#c8d8ee' }}>
                          {oid.oid_name || '—'}
                        </td>
                        <td className="px-4 py-2.5 font-mono text-xs max-w-xs truncate" style={{ color: '#00ff88' }}>
                          {oid.value || '—'}
                        </td>
                        <td className="px-4 py-2.5 font-mono text-xs" style={{ color: '#7c3aed' }}>
                          {oid.type || '—'}
                        </td>
                        <td className="px-4 py-2.5 font-mono text-xs" style={{ color: '#8899bb' }}>
                          {oid.mib || '—'}
                        </td>
                        <td className="px-4 py-2.5">
                          <SNMPStatusBadge status={oid.supported ? 'supported' : 'unsupported'} size="xs" />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </GlassCard>
          )}
        </>
      )}

      {/* OID Detail Modal */}
      {selected && <OIDDetail oid={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}
