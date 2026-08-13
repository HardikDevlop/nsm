import { useState } from 'react'
import { useNavigate } from 'react-router'
import GlassCard from '../components/GlassCard'
import { useAddSNMPDevice, useTestSNMPConnection } from '../hooks/useSnmpQueries'
import { useAuth } from '../components/AuthContext'

const SECURITY_LEVELS = ['noAuthNoPriv', 'authNoPriv', 'authPriv']
const AUTH_PROTOCOLS = ['MD5', 'SHA']
const PRIVACY_PROTOCOLS = ['DES', 'AES']

export default function AddSNMPDevicePage() {
  const navigate = useNavigate()
  const { isSuperAdmin } = useAuth()
  const addDevice = useAddSNMPDevice()
  const testSNMP = useTestSNMPConnection()

  const [step, setStep] = useState<'form' | 'test' | 'complete'>('form')
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<{ reachable: boolean; message: string } | null>(null)
  const [testing, setTesting] = useState(false)
  const [adding, setAdding] = useState(false)

  const [formData, setFormData] = useState({
    ip_address: '',
    name: '',
    hostname: '',
    description: '',
    snmp_version: 'v3' as 'v2c' | 'v3',
    snmp_port: 161,
    community_string: '',
    username: 'Agnigate',
    auth_protocol: 'MD5',
    auth_password: '',
    privacy_protocol: 'DES',
    privacy_password: '',
    security_level: 'authPriv',
    site_id: undefined as number | undefined,
    mac_address: '',
    vendor_override: '',
    model_override: '',
    device_type_override: '',
    auto_discover: true,
  })

  const [showV3Fields, setShowV3Fields] = useState(true)

  const handleChange = (field: string, value: any) => {
    setFormData(prev => ({ ...prev, [field]: value }))
    setError(null)
    setSuccess(null)
  }

  const handleTestSNMP = async () => {
    if (!formData.ip_address) {
      setError('IP Address is required')
      return
    }

    setTesting(true)
    setError(null)
    setTestResult(null)

    try {
      // Create a temporary device to test, or use the test endpoint directly
      // For now, we'll need a device ID to test. Let's create a temporary one.
      // Actually, the test-snmp endpoint requires a device ID. We'll need to add the device first,
      // then test, or we can modify the backend to accept credentials directly.
      // For now, let's show a message that the device needs to be added first.
      setTestResult({ reachable: false, message: 'Device must be added first. Add the device, then use the Test SNMP button on the device details page.' })
    } catch (err) {
      setTestResult({ reachable: false, message: err instanceof Error ? err.message : 'Test failed' })
    } finally {
      setTesting(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setSuccess(null)

    if (!formData.ip_address) {
      setError('IP Address is required')
      return
    }
    if (!formData.name && !formData.hostname) {
      setError('Device Name or Hostname is required')
      return
    }
    if (formData.snmp_version === 'v3' && !formData.username) {
      setError('SNMPv3 requires a username')
      return
    }
    if (formData.snmp_version === 'v3' && formData.security_level === 'authPriv' && (!formData.auth_password || !formData.privacy_password)) {
      setError('SNMPv3 authPriv requires both auth and privacy passwords')
      return
    }
    if (formData.snmp_version === 'v3' && formData.security_level === 'authNoPriv' && !formData.auth_password) {
      setError('SNMPv3 authNoPriv requires auth password')
      return
    }

    setAdding(true)
    try {
      const result = await addDevice.mutateAsync({
        ...formData,
        site_id: formData.site_id || undefined,
        mac_address: formData.mac_address || undefined,
      })
      setSuccess(`Device added successfully! ${result.discovery?.reachable ? 'SNMP discovery completed.' : 'Run discovery to detect device capabilities.'}`)
      setTimeout(() => {
        if (result.device?.id) {
          navigate(`/snmp/devices/${result.device.id}`)
        } else {
          navigate('/snmp/devices')
        }
      }, 1500)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add device')
    } finally {
      setAdding(false)
    }
  }

  const clearMessages = () => {
    setError(null)
    setSuccess(null)
    setTestResult(null)
  }

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-5 max-w-3xl mx-auto">
      {/* Breadcrumb */}
      <div className="flex items-center gap-2 font-mono text-xs" style={{ color: '#667799' }}>
        <button onClick={() => navigate('/snmp/devices')} className="hover:text-cyan-400 transition-colors">DEVICES</button>
        <span>/</span>
        <span style={{ color: '#c8d8ee' }}>ADD DEVICE</span>
      </div>

      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div>
          <h1 className="font-display font-bold text-xl sm:text-2xl tracking-widest neon-cyan">ADD SNMP DEVICE</h1>
          <p className="font-mono text-xs mt-0.5" style={{ color: '#8899bb' }}>
            Enter device details and SNMP credentials
          </p>
        </div>
        <button onClick={() => navigate('/snmp/devices')}
          className="glass-bright px-3 py-1.5 rounded font-mono text-xs hover:bg-gray-400/10"
          style={{ border: '1px solid rgba(136,153,187,0.25)', color: '#8899bb' }}>
          CANCEL
        </button>
      </div>

      {error && (
        <div className="font-mono text-xs p-3 rounded" style={{ color: '#ff3366', background: 'rgba(255,51,102,0.1)', border: '1px solid rgba(255,51,102,0.3)' }}>
          {error}
        </div>
      )}

      {success && (
        <div className="font-mono text-xs p-3 rounded" style={{ color: '#00ff88', background: 'rgba(0,255,136,0.1)', border: '1px solid rgba(0,255,136,0.3)' }}>
          {success}
        </div>
      )}

      <GlassCard className="p-4 space-y-4">
        <div className="font-display font-bold text-sm tracking-wider neon-cyan mb-4">BASIC INFORMATION</div>
        <div className="space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className="font-mono text-[10px] block mb-1" style={{ color: '#667799' }}>IP ADDRESS *</label>
              <input
                type="text"
                value={formData.ip_address}
                onChange={(e) => handleChange('ip_address', e.target.value)}
                placeholder="192.168.1.1"
                className="w-full glass-bright rounded px-3 py-2 font-mono text-xs"
                style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.7)' }}
              />
            </div>
            <div>
              <label className="font-mono text-[10px] block mb-1" style={{ color: '#667799' }}>DEVICE NAME *</label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => handleChange('name', e.target.value)}
                placeholder="Core-Switch-01"
                className="w-full glass-bright rounded px-3 py-2 font-mono text-xs"
                style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.7)' }}
              />
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className="font-mono text-[10px] block mb-1" style={{ color: '#667799' }}>HOSTNAME</label>
              <input
                type="text"
                value={formData.hostname}
                onChange={(e) => handleChange('hostname', e.target.value)}
                placeholder="core-switch-01.example.com"
                className="w-full glass-bright rounded px-3 py-2 font-mono text-xs"
                style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.7)' }}
              />
            </div>
            <div>
              <label className="font-mono text-[10px] block mb-1" style={{ color: '#667799' }}>MAC ADDRESS</label>
              <input
                type="text"
                value={formData.mac_address}
                onChange={(e) => handleChange('mac_address', e.target.value)}
                placeholder="00:11:22:33:44:55"
                className="w-full glass-bright rounded px-3 py-2 font-mono text-xs"
                style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.7)' }}
              />
            </div>
          </div>
          <div>
            <label className="font-mono text-[10px] block mb-1" style={{ color: '#667799' }}>DESCRIPTION</label>
            <textarea
              value={formData.description}
              onChange={(e) => handleChange('description', e.target.value)}
              placeholder="Optional description..."
              rows={2}
              className="w-full glass-bright rounded px-3 py-2 font-mono text-xs resize-none"
              style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.7)' }}
            />
          </div>
        </div>
      </GlassCard>

      <GlassCard className="p-4 space-y-4">
        <div className="font-display font-bold text-sm tracking-wider neon-cyan mb-4">SNMP CONFIGURATION</div>
        <div className="space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className="font-mono text-[10px] block mb-1" style={{ color: '#667799' }}>SNMP VERSION *</label>
              <select
                value={formData.snmp_version}
                onChange={(e) => { handleChange('snmp_version', e.target.value); setShowV3Fields(e.target.value === 'v3') }}
                className="w-full glass-bright rounded px-3 py-2 font-mono text-xs"
                style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.7)' }}
              >
                <option value="v2c">SNMPv2c</option>
                <option value="v3">SNMPv3</option>
              </select>
            </div>
            <div>
              <label className="font-mono text-[10px] block mb-1" style={{ color: '#667799' }}>SNMP PORT</label>
              <input
                type="number"
                value={formData.snmp_port}
                onChange={(e) => handleChange('snmp_port', Number(e.target.value))}
                min="1"
                max="65535"
                className="w-full glass-bright rounded px-3 py-2 font-mono text-xs"
                style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.7)' }}
              />
            </div>
          </div>

          {/* SNMPv2c Community */}
          {!showV3Fields && (
            <div>
              <label className="font-mono text-[10px] block mb-1" style={{ color: '#667799' }}>COMMUNITY STRING *</label>
              <input
                type="text"
                value={formData.community_string}
                onChange={(e) => handleChange('community_string', e.target.value)}
                placeholder="public"
                className="w-full glass-bright rounded px-3 py-2 font-mono text-xs"
                style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.7)' }}
              />
            </div>
          )}

          {/* SNMPv3 Fields */}
          {showV3Fields && (
            <div className="space-y-3 border-l-2 pl-4" style={{ borderColor: 'rgba(124,58,237,0.5)' }}>
              <div className="font-mono text-xs mb-2" style={{ color: '#7c3aed' }}>SNMPv3 Credentials</div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label className="font-mono text-[10px] block mb-1" style={{ color: '#667799' }}>USERNAME *</label>
                  <input
                    type="text"
                    value={formData.username}
                    onChange={(e) => handleChange('username', e.target.value)}
                    placeholder="Agnigate"
                    className="w-full glass-bright rounded px-3 py-2 font-mono text-xs"
                    style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.7)' }}
                  />
                </div>
                <div>
                  <label className="font-mono text-[10px] block mb-1" style={{ color: '#667799' }}>SECURITY LEVEL *</label>
                  <select
                    value={formData.security_level}
                    onChange={(e) => handleChange('security_level', e.target.value)}
                    className="w-full glass-bright rounded px-3 py-2 font-mono text-xs"
                    style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.7)' }}
                  >
                    <option value="noAuthNoPriv">noAuthNoPriv</option>
                    <option value="authNoPriv">authNoPriv</option>
                    <option value="authPriv">authPriv</option>
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label className="font-mono text-[10px] block mb-1" style={{ color: '#667799' }}>AUTH PROTOCOL</label>
                  <select
                    value={formData.auth_protocol}
                    onChange={(e) => handleChange('auth_protocol', e.target.value)}
                    className="w-full glass-bright rounded px-3 py-2 font-mono text-xs"
                    style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.7)' }}
                  >
                    {AUTH_PROTOCOLS.map(p => <option key={p} value={p}>{p}</option>)}
                  </select>
                </div>
                <div>
                  <label className="font-mono text-[10px] block mb-1" style={{ color: '#667799' }}>PRIVACY PROTOCOL</label>
                  <select
                    value={formData.privacy_protocol}
                    onChange={(e) => handleChange('privacy_protocol', e.target.value)}
                    className="w-full glass-bright rounded px-3 py-2 font-mono text-xs"
                    style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.7)' }}
                  >
                    {PRIVACY_PROTOCOLS.map(p => <option key={p} value={p}>{p}</option>)}
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label className="font-mono text-[10px] block mb-1" style={{ color: '#667799' }}>AUTH PASSWORD</label>
                  <input
                    type="password"
                    value={formData.auth_password}
                    onChange={(e) => handleChange('auth_password', e.target.value)}
                    placeholder="Gate@123"
                    className="w-full glass-bright rounded px-3 py-2 font-mono text-xs"
                    style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.7)' }}
                  />
                </div>
                <div>
                  <label className="font-mono text-[10px] block mb-1" style={{ color: '#667799' }}>PRIVACY PASSWORD</label>
                  <input
                    type="password"
                    value={formData.privacy_password}
                    onChange={(e) => handleChange('privacy_password', e.target.value)}
                    placeholder="Gate@123"
                    className="w-full glass-bright rounded px-3 py-2 font-mono text-xs"
                    style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.7)' }}
                  />
                </div>
              </div>
            </div>
          )}
        </div>
      </GlassCard>

      <GlassCard className="p-4 space-y-4">
        <div className="font-display font-bold text-sm tracking-wider neon-cyan mb-4">ADVANCED OPTIONS</div>
        <div className="space-y-3">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className="font-mono text-[10px] block mb-1" style={{ color: '#667799' }}>SITE ID</label>
              <input
                type="number"
                value={formData.site_id || ''}
                onChange={(e) => handleChange('site_id', e.target.value ? Number(e.target.value) : undefined)}
                placeholder="Optional"
                className="w-full glass-bright rounded px-3 py-2 font-mono text-xs"
                style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.7)' }}
              />
            </div>
            <div>
              <label className="font-mono text-[10px] block mb-1" style={{ color: '#667799' }}>VENDOR OVERRIDE</label>
              <input
                type="text"
                value={formData.vendor_override}
                onChange={(e) => handleChange('vendor_override', e.target.value)}
                placeholder="e.g., Cisco, Fortinet"
                className="w-full glass-bright rounded px-3 py-2 font-mono text-xs"
                style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.7)' }}
              />
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <label className="font-mono text-[10px] block mb-1" style={{ color: '#667799' }}>MODEL OVERRIDE</label>
              <input
                type="text"
                value={formData.model_override}
                onChange={(e) => handleChange('model_override', e.target.value))
                placeholder="e.g., Catalyst 9300"
                className="w-full glass-bright rounded px-3 py-2 font-mono text-xs"
                style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.7)' }}
              />
            </div>
            <div>
              <label className="font-mono text-[10px] block mb-1" style={{ color: '#667799' }}>DEVICE TYPE OVERRIDE</label>
              <input
                type="text"
                value={formData.device_type_override}
                onChange={(e) => handleChange('device_type_override', e.target.value))
                placeholder="e.g., switch, router, firewall"
                className="w-full glass-bright rounded px-3 py-2 font-mono text-xs"
                style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.7)' }}
              />
            </div>
          </div>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={formData.auto_discover}
              onChange={(e) => handleChange('auto_discover', e.target.checked)}
              className="w-4 h-4 accent-cyan-400"
            />
            <span className="font-mono text-xs" style={{ color: '#c8d8ee' }}>Auto-discover device capabilities after adding</span>
          </label>
        </div>
      </GlassCard>

      {/* Actions */}
      <div className="flex flex-wrap gap-3">
        <button
          onClick={handleSubmit}
          disabled={adding}
          className="flex-1 md:flex-none px-4 py-2 rounded font-mono text-xs font-semibold transition-all"
          style={{
            background: 'rgba(0,255,136,0.15)',
            color: '#00ff88',
            border: '1px solid rgba(0,255,136,0.4)',
            opacity: adding ? 0.6 : 1,
            cursor: adding ? 'not-allowed' : 'pointer',
          }}
        >
          {adding ? 'ADDING...' : 'ADD DEVICE'}
        </button>
        <button
          onClick={() => navigate('/snmp/devices')}
          className="flex-1 md:flex-none px-4 py-2 rounded font-mono text-xs font-semibold transition-all"
          style={{ background: 'rgba(136,153,187,0.15)', color: '#8899bb', border: '1px solid rgba(136,153,187,0.4)' }}
        >
          CANCEL
        </button>
      </div>
    </div>
  )
}