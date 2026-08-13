import { useParams, useNavigate } from 'react-router'
import { useEffect, useState } from 'react'
import GlassCard from '../components/GlassCard'
import { useDeviceCapabilities } from '../modules/useSNMPModules'
import { listSNMPDevices, type DeviceRecord } from '../lib/api'

export default function SNMPCapabilities() {
  const { deviceId } = useParams<{ deviceId: string }>()
  const navigate = useNavigate()
  const id = Number(deviceId)
  
  const [devices, setDevices] = useState<DeviceRecord[]>([])
  const [selectedDeviceId, setSelectedDeviceId] = useState<number | null>(id || null)
  
  const { data: capabilities, isLoading, error } = useDeviceCapabilities(selectedDeviceId)
  
  useEffect(() => {
    const loadDevices = async () => {
      try {
        const devs = await listSNMPDevices()
        setDevices(devs)
        if (!selectedDeviceId && devs.length > 0) {
          setSelectedDeviceId(devs[0].id)
        }
      } catch (err) {
        console.error('Failed to load devices:', err)
      }
    }
    void loadDevices()
  }, [selectedDeviceId])

  const handleDeviceChange = (devId: number) => {
    setSelectedDeviceId(devId)
    navigate(`/snmp/devices/${devId}/capabilities`)
  }

  const currentDevice = devices.find(d => d.id === selectedDeviceId)

  const moduleCategories = [
    { category: 'System', modules: ['system', 'cpu', 'memory', 'storage'] },
    { category: 'Network', modules: ['interfaces', 'vlan', 'lldp', 'routing'] },
    { category: 'Advanced', modules: ['environment', 'topology', 'oids', 'polling'] }
  ]

  return (
    <div className="p-4 md:p-6 space-y-4 md:space-y-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
        <div className="flex-1 min-w-0">
          <h1 className="font-display font-bold text-xl sm:text-2xl tracking-widest neon-cyan">
            SNMP CAPABILITIES
          </h1>
          <p className="font-mono text-xs mt-0.5" style={{ color: '#8899bb' }}>
            Device Module Support & Feature Overview
          </p>
        </div>
        
        {/* Device Selector */}
        {devices.length > 0 && (
          <select
            value={selectedDeviceId || ''}
            onChange={(e) => handleDeviceChange(Number(e.target.value))}
            className="glass-bright px-3 py-2 rounded font-mono text-xs min-h-[44px]"
            style={{ border: '1px solid rgba(0,212,255,0.25)', color: '#c8d8ee', background: 'rgba(8,25,55,0.6)' }}
          >
            {devices.map(dev => (
              <option key={dev.id} value={dev.id}>
                {dev.hostname || dev.ip_address}
              </option>
            ))}
          </select>
        )}
      </div>

      {currentDevice && (
        <GlassCard className="p-4">
          <div className="flex items-center gap-3 mb-3">
            <h2 className="font-display font-bold text-lg tracking-wider neon-cyan">
              {currentDevice.hostname || currentDevice.ip_address}
            </h2>
            <span className="font-mono text-xs px-2 py-1 rounded" style={{ 
              background: 'rgba(0,255,136,0.15)', 
              color: '#00ff88',
              border: '1px solid rgba(0,255,136,0.3)'
            }}>
              {currentDevice.device_type}
            </span>
          </div>
        </GlassCard>
      )}

      {isLoading && (
        <div className="flex items-center justify-center p-12">
          <div className="font-mono text-sm" style={{ color: '#00d4ff' }}>
            Loading capabilities...
          </div>
        </div>
      )}

      {error && (
        <div className="font-mono text-xs p-4 rounded" style={{ color: '#ff3366', background: 'rgba(255,51,102,0.1)', border: '1px solid rgba(255,51,102,0.3)' }}>
          Failed to load capabilities: {error.message}
        </div>
      )}

      {capabilities && (
        <div className="space-y-6">
          {moduleCategories.map(({ category, modules }) => (
            <div key={category}>
              <h3 className="font-display font-bold text-base mb-4 tracking-wider" style={{ color: '#00d4ff' }}>
                {category.toUpperCase()}
              </h3>
              
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {modules.map(module => {
                  const isSupported = capabilities[module] === true
                  const bgColor = isSupported ? 'rgba(0,255,136,0.1)' : 'rgba(255,51,102,0.1)'
                  const borderColor = isSupported ? 'rgba(0,255,136,0.2)' : 'rgba(255,51,102,0.2)'
                  const textColor = isSupported ? '#00ff88' : '#ff3366'
                  
                  return (
                    <GlassCard 
                      key={module}
                      className="p-4 text-center cursor-pointer hover:scale-[1.02] transition-all"
                      style={{ background: bgColor, border: `1px solid ${borderColor}` }}
                      onClick={() => isSupported && navigate(`/snmp/devices/${selectedDeviceId}/${module}`)}
                    >
                      <div className="font-display font-bold text-sm mb-2" style={{ color: textColor }}>
                        {module.toUpperCase()}
                      </div>
                      <div className="font-mono text-xs" style={{ color: '#8899bb' }}>
                        {isSupported ? 'Supported' : 'Not Available'}
                      </div>
                      {isSupported && (
                        <div className="mt-2">
                          <div className="w-2 h-2 mx-auto rounded-full" style={{ 
                            backgroundColor: '#00ff88',
                            boxShadow: '0 0 6px #00ff88'
                          }} />
                        </div>
                      )}
                    </GlassCard>
                  )
                })}
              </div>
            </div>
          ))}
          
          <div className="mt-8">
            <h3 className="font-display font-bold text-base mb-4 tracking-wider" style={{ color: '#00d4ff' }}>
              QUICK ACTIONS
            </h3>
            
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <button
                onClick={() => navigate(`/snmp/dashboard/${selectedDeviceId}`)}
                className="p-3 rounded font-mono text-xs transition-all"
                style={{ background: 'rgba(0,212,255,0.15)', color: '#00d4ff', border: '1px solid rgba(0,212,255,0.4)' }}
              >
                View Dashboard
              </button>
              <button
                onClick={() => navigate(`/snmp/devices/${selectedDeviceId}`)}
                className="p-3 rounded font-mono text-xs transition-all"
                style={{ background: 'rgba(0,255,136,0.15)', color: '#00ff88', border: '1px solid rgba(0,255,136,0.4)' }}
              >
                Device Details
              </button>
              <button
                onClick={() => navigate(`/snmp/devices/${selectedDeviceId}/monitoring`)}
                className="p-3 rounded font-mono text-xs transition-all"
                style={{ background: 'rgba(255,170,0,0.15)', color: '#ffaa00', border: '1px solid rgba(255,170,0,0.4)' }}
              >
                Configure Monitoring
              </button>
              <button
                onClick={() => navigate('/snmp-monitoring')}
                className="p-3 rounded font-mono text-xs transition-all"
                style={{ background: 'rgba(138,43,226,0.15)', color: '#8a2be2', border: '1px solid rgba(138,43,226,0.4)' }}
              >
                All Devices
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}