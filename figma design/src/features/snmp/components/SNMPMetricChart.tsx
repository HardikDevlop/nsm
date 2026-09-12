import { useEffect, useRef } from 'react'

interface DataPoint {
  timestamp: string
  value: number
  value2?: number
}

interface SNMPMetricChartProps {
  data: DataPoint[]
  height?: number
  color?: string
  color2?: string
  label?: string
  label2?: string
  unit?: string
  showArea?: boolean
  showGrid?: boolean
  showAxes?: boolean
  noDataMessage?: string
  className?: string
}

function formatTime(ts: string): string {
  try {
    const d = new Date(ts)
    return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false })
  } catch {
    return ''
  }
}

export default function SNMPMetricChart({
  data,
  height = 120,
  color = '#00d4ff',
  color2 = '#00ff88',
  label,
  label2,
  unit = '',
  showArea = true,
  showGrid = true,
  showAxes = true,
  noDataMessage = 'No Historical Data Yet',
  className = '',
}: SNMPMetricChartProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  // Poll APIs are not required to return samples in display order. Normalize
  // here so every chart has a truthful chronological x-axis and never plots
  // null/NaN values as zero.
  const plottedData = (data || [])
    .filter(d => Number.isFinite(d.value) && (!Number.isFinite(d.value2) || d.value2 !== undefined))
    .slice()
    .sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    const dpr = window.devicePixelRatio || 1
    const w = canvas.offsetWidth
    const h = canvas.offsetHeight
    canvas.width = w * dpr
    canvas.height = h * dpr
    ctx.scale(dpr, dpr)

    ctx.clearRect(0, 0, w, h)

    if (plottedData.length < 2) return

    const padLeft = showAxes ? 40 : 8
    const padRight = 8
    const padTop = 8
    const padBottom = showAxes ? 24 : 8

    const allValues = plottedData.flatMap(d => [d.value, ...(d.value2 !== undefined && Number.isFinite(d.value2) ? [d.value2] : [])])
    const maxVal = Math.max(...allValues, 1)
    const minVal = Math.min(...allValues, 0)
    const range = maxVal - minVal || 1

    const chartW = w - padLeft - padRight
    const chartH = h - padTop - padBottom

    const toX = (i: number) => padLeft + (i / (plottedData.length - 1)) * chartW
    const toY = (v: number) => padTop + chartH - ((v - minVal) / range) * chartH

    // Grid lines
    if (showGrid) {
      ctx.strokeStyle = 'rgba(136,153,187,0.08)'
      ctx.lineWidth = 1
      const gridLines = 4
      for (let i = 0; i <= gridLines; i++) {
        const y = padTop + (i / gridLines) * chartH
        ctx.beginPath()
        ctx.moveTo(padLeft, y)
        ctx.lineTo(w - padRight, y)
        ctx.stroke()
      }
    }

    // Y-axis labels
    if (showAxes) {
      ctx.fillStyle = '#667799'
      ctx.font = '9px monospace'
      ctx.textAlign = 'right'
      const gridLines = 4
      for (let i = 0; i <= gridLines; i++) {
        const val = minVal + ((gridLines - i) / gridLines) * range
        const y = padTop + (i / gridLines) * chartH
        ctx.fillText(`${Math.round(val)}${unit}`, padLeft - 4, y + 3)
      }
    }

    const drawLine = (field: 'value' | 'value2', lineColor: string) => {
      if (field === 'value2' && !plottedData.some(d => d.value2 !== undefined && Number.isFinite(d.value2))) return

      const getValue = (d: DataPoint) => field === 'value' ? d.value : d.value2 as number

      // Area fill
      if (showArea) {
        const gradient = ctx.createLinearGradient(0, padTop, 0, padTop + chartH)
        gradient.addColorStop(0, `${lineColor}30`)
        gradient.addColorStop(1, `${lineColor}00`)
        ctx.beginPath()
        ctx.moveTo(toX(0), padTop + chartH)
        plottedData.forEach((d, i) => ctx.lineTo(toX(i), toY(getValue(d))))
        ctx.lineTo(toX(plottedData.length - 1), padTop + chartH)
        ctx.closePath()
        ctx.fillStyle = gradient
        ctx.fill()
      }

      // Line
      ctx.beginPath()
      ctx.strokeStyle = lineColor
      ctx.lineWidth = 1.5
      ctx.lineJoin = 'round'
      plottedData.forEach((d, i) => {
        const x = toX(i)
        const y = toY(getValue(d))
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y)
      })
      ctx.stroke()
    }

    drawLine('value', color)
    drawLine('value2', color2)

    // X-axis time labels
    if (showAxes && plottedData.length >= 2) {
      ctx.fillStyle = '#556677'
      ctx.font = '9px monospace'
      ctx.textAlign = 'center'
      const labelCount = Math.min(4, plottedData.length)
      for (let i = 0; i < labelCount; i++) {
        const idx = Math.round((i / (labelCount - 1)) * (plottedData.length - 1))
        const x = toX(idx)
        const y = h - padBottom + 12
        ctx.fillText(formatTime(plottedData[idx].timestamp), x, y)
      }
    }
  }, [plottedData, color, color2, showArea, showGrid, showAxes, unit])

  if (plottedData.length < 2) {
    return (
      <div
        className={`flex items-center justify-center ${className}`}
        style={{ height, background: 'rgba(0,0,0,0.15)', borderRadius: 6, border: '1px solid rgba(0,212,255,0.06)' }}
      >
        <span className="font-mono text-xs" style={{ color: '#556677' }}>{noDataMessage}</span>
      </div>
    )
  }

  return (
    <div className={`relative ${className}`} style={{ height }}>
      {(label || label2) && (
        <div className="absolute top-1 right-2 flex gap-3 z-10">
          {label && (
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-0.5 rounded" style={{ background: color }} />
              <span className="font-mono text-[9px]" style={{ color: '#8899bb' }}>{label}</span>
            </div>
          )}
          {label2 && plottedData.some(d => d.value2 !== undefined && Number.isFinite(d.value2)) && (
            <div className="flex items-center gap-1.5">
              <div className="w-3 h-0.5 rounded" style={{ background: color2 }} />
              <span className="font-mono text-[9px]" style={{ color: '#8899bb' }}>{label2}</span>
            </div>
          )}
        </div>
      )}
      <canvas
        ref={canvasRef}
        style={{ width: '100%', height: '100%' }}
      />
    </div>
  )
}
