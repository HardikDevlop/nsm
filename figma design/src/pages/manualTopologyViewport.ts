export type Viewport = { zoom: number; pan: { x: number; y: number } }
export function readViewports(raw: string | null): Record<string, Viewport> {
  try {
    const parsed = JSON.parse(raw || '{}')
    if (!parsed || typeof parsed !== 'object') return {}
    return Object.fromEntries(Object.entries(parsed).filter(([, value]) => {
      const item = value as Viewport
      return item && Number.isFinite(item.zoom) && item.zoom >= 0.25 && item.zoom <= 3 &&
        Number.isFinite(item.pan?.x) && Number.isFinite(item.pan?.y)
    })) as Record<string, Viewport>
  } catch { return {} }
}
export function centeredViewport(devices: { x: number; y: number }[]): Viewport {
  if (!devices.length) return { zoom: 1, pan: { x: 0, y: 0 } }
  const minX = Math.min(...devices.map(d => d.x - 140)), maxX = Math.max(...devices.map(d => d.x + 140))
  const minY = Math.min(...devices.map(d => d.y - 100)), maxY = Math.max(...devices.map(d => d.y + 100))
  const zoom = Math.min(1.5, Math.max(0.25, Math.min(1400 / (maxX - minX + 100), 820 / (maxY - minY + 100))))
  return { zoom, pan: { x: 700 - (minX + maxX) / 2 * zoom, y: 410 - (minY + maxY) / 2 * zoom } }
}

export function zoomViewport(current: Viewport, requestedZoom: number): Viewport {
  const zoom = Math.min(3, Math.max(0.25, requestedZoom))
  const ratio = zoom / current.zoom
  return { zoom, pan: { x: 700 - (700 - current.pan.x) * ratio, y: 410 - (410 - current.pan.y) * ratio } }
}
