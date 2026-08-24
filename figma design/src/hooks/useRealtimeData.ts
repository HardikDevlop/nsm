import { useState, useEffect, useRef, useCallback } from 'react'

interface UseRealtimeDataOptions<T> {
  fetchFunction: () => Promise<T>
  refreshInterval: number  // seconds
  timeWindow: number      // seconds - how much historical data to keep
  enabled: boolean
  onData?: (data: T) => void
  onError?: (error: string) => void
}

interface RealtimeDataState<T> {
  currentData: T | null
  historicalData: Array<{ timestamp: number; data: T }>
  loading: boolean
  error: string | null
  lastUpdate: number | null
  nextRefresh: number | null
}

export function useRealtimeData<T>({
  fetchFunction,
  refreshInterval,
  timeWindow,
  enabled,
  onData,
  onError
}: UseRealtimeDataOptions<T>) {
  
  const [state, setState] = useState<RealtimeDataState<T>>({
    currentData: null,
    historicalData: [],
    loading: false,
    error: null,
    lastUpdate: null,
    nextRefresh: null
  })
  
  const intervalRef = useRef<NodeJS.Timeout | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)
  
  // Fetch data function
  const fetchData = useCallback(async () => {
    if (!enabled) return
    
    // Cancel previous request
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
    }
    
    abortControllerRef.current = new AbortController()
    
    setState(prev => ({ ...prev, loading: true, error: null }))
    
    try {
      const data = await fetchFunction()
      const timestamp = Date.now()
      
      setState(prev => {
        // Add new data to history
        const newHistoricalData = [
          ...prev.historicalData,
          { timestamp, data }
        ].filter(item => timestamp - item.timestamp <= timeWindow * 1000)
        
        return {
          ...prev,
          currentData: data,
          historicalData: newHistoricalData,
          loading: false,
          lastUpdate: timestamp,
          nextRefresh: timestamp + (refreshInterval * 1000)
        }
      })
      
      onData?.(data)
      
    } catch (error) {
      if (error instanceof Error && error.name === 'AbortError') {
        return // Ignore aborted requests
      }
      
      const errorMessage = error instanceof Error ? error.message : 'Fetch failed'
      setState(prev => ({
        ...prev,
        loading: false,
        error: errorMessage
      }))
      
      onError?.(errorMessage)
    }
  }, [fetchFunction, enabled, timeWindow, refreshInterval, onData, onError])
  
  // Setup interval
  useEffect(() => {
    if (!enabled) {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
      return
    }
    
    // Initial fetch
    fetchData()
    
    // Setup interval
    if (intervalRef.current) {
      clearInterval(intervalRef.current)
    }
    
    intervalRef.current = setInterval(fetchData, refreshInterval * 1000)
    
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
      }
    }
  }, [enabled, refreshInterval, fetchData])
  
  // Clean up old data when time window changes
  useEffect(() => {
    setState(prev => ({
      ...prev,
      historicalData: prev.historicalData.filter(
        item => Date.now() - item.timestamp <= timeWindow * 1000
      )
    }))
  }, [timeWindow])
  
  // Manual refresh
  const refresh = useCallback(() => {
    fetchData()
  }, [fetchData])
  
  // Get data within time window
  const getDataInWindow = useCallback((seconds?: number) => {
    const windowMs = (seconds || timeWindow) * 1000
    const cutoff = Date.now() - windowMs
    
    return state.historicalData.filter(item => item.timestamp >= cutoff)
  }, [state.historicalData, timeWindow])
  
  // Get latest N data points
  const getLatestData = useCallback((count: number) => {
    return state.historicalData.slice(-count)
  }, [state.historicalData])
  
  // Calculate data rate (points per second)
  const getDataRate = useCallback(() => {
    if (state.historicalData.length < 2) return 0
    
    const timeSpan = state.historicalData[state.historicalData.length - 1].timestamp - 
                    state.historicalData[0].timestamp
    
    return timeSpan > 0 ? (state.historicalData.length - 1) / (timeSpan / 1000) : 0
  }, [state.historicalData])
  
  return {
    // Current state
    data: state.currentData,
    loading: state.loading,
    error: state.error,
    lastUpdate: state.lastUpdate,
    nextRefresh: state.nextRefresh,
    
    // Historical data
    historicalData: state.historicalData,
    dataCount: state.historicalData.length,
    
    // Controls
    refresh,
    
    // Data access
    getDataInWindow,
    getLatestData,
    getDataRate,
    
    // Computed values
    isStale: state.lastUpdate ? Date.now() - state.lastUpdate > (refreshInterval * 2000) : false,
    timeToNextRefresh: state.nextRefresh ? Math.max(0, state.nextRefresh - Date.now()) : 0
  }
}

// Import API functions
import { listDevices, listDeviceMetrics, listAlerts } from '../lib/api'

// Specialized hooks for common data types
export function useRealtimeDevices(refreshInterval = 5, timeWindow = 30, enabled = true) {
  return useRealtimeData({
    fetchFunction: listDevices,
    refreshInterval,
    timeWindow,
    enabled
  })
}

export function useRealtimeMetrics(refreshInterval = 2, timeWindow = 60, enabled = true) {
  const fetchMetrics = useCallback(async () => {
    try {
      return await listDeviceMetrics(undefined, { limit: 50 })
    } catch (error) {
      if (error instanceof Error && error.message.includes('403')) return []
      throw error
    }
  }, [])

  return useRealtimeData({
    // Metrics are supplementary to the dashboard. A role may be allowed to
    // view devices without having the separate metrics-management permission.
    // In that case keep the dashboard operational and show no chart points.
    fetchFunction: fetchMetrics,
    refreshInterval,
    timeWindow,
    enabled
  })
}

export function useRealtimeAlerts(refreshInterval = 10, timeWindow = 300, enabled = true) {
  return useRealtimeData({
    fetchFunction: listAlerts,
    refreshInterval,
    timeWindow,
    enabled
  })
}
