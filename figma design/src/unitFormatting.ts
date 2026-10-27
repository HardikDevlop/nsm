export type UnitFormatOptions = { decimals?: number; na?: string }
const DEFAULT_NA = "N/A"
const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value)
const formatScaled = (value: number, units: readonly string[], base: number, options: UnitFormatOptions = {}) => {
  if (!finite(value)) return options.na ?? DEFAULT_NA
  const decimals = options.decimals ?? 1
  const sign = value < 0 ? "-" : ""
  let scaled = Math.abs(value); let index = 0
  while (scaled >= base && index < units.length - 1) { scaled /= base; index += 1 }
  return `${sign}${scaled.toFixed(index === 0 ? 0 : decimals)} ${units[index]}`
}
export function formatBytesDecimal(value: number | null | undefined, options?: UnitFormatOptions) { return formatScaled(value as number, ["B", "KB", "MB", "GB", "TB", "PB"], 1000, options) }
export function formatBytesBinary(value: number | null | undefined, options?: UnitFormatOptions) { return formatScaled(value as number, ["B", "KiB", "MiB", "GiB", "TiB", "PiB"], 1024, options) }
export function formatBitsPerSecond(value: number | null | undefined, options?: UnitFormatOptions) { return formatScaled(value as number, ["bps", "Kbps", "Mbps", "Gbps", "Tbps", "Pbps"], 1000, options) }
export function formatBytesPerSecond(value: number | null | undefined, options?: UnitFormatOptions) { return formatScaled(value as number, ["B/s", "KiB/s", "MiB/s", "GiB/s", "TiB/s", "PiB/s"], 1024, options) }
export function formatPercentage(value: number | null | undefined, options: UnitFormatOptions = {}) { return finite(value) ? `${value.toFixed(options.decimals ?? 1)}%` : options.na ?? DEFAULT_NA }
export function formatLatency(value: number | null | undefined, options: UnitFormatOptions = {}) { return finite(value) ? `${value.toFixed(options.decimals ?? 1)} ms` : options.na ?? DEFAULT_NA }
export function formatUptime(value: number | null | undefined, options: UnitFormatOptions = {}) { if (!finite(value) || value < 0) return options.na ?? DEFAULT_NA; const s = Math.floor(value); const d = Math.floor(s / 86400); const h = Math.floor((s % 86400) / 3600); const m = Math.floor((s % 3600) / 60); const sec = s % 60; return d ? `${d}d ${h}h ${m}m` : h ? `${h}h ${m}m` : m ? `${m}m ${sec}s` : `${sec}s` }
export function formatFrequency(value: number | null | undefined, options: UnitFormatOptions = {}) { return formatScaled(value as number, ["Hz", "kHz", "MHz", "GHz", "THz"], 1000, options) }
