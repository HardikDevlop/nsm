type PortLink = { id: string; from: string; to: string; fromPort?: string; toPort?: string }
type Position = { id: string; x: number; y: number }

export function portEndpoint(device: Position, link: PortLink, links: PortLink[], devices: Position[] = []) {
  const sideFor = (item: PortLink) => {
    const other = devices.find(d => d.id === (item.from === device.id ? item.to : item.from))
    if (!other) return "right"
    const dx = other.x - device.x, dy = other.y - device.y
    return Math.abs(dx) / 70 >= Math.abs(dy) / 46
      ? dx >= 0 ? "right" : "left"
      : dy >= 0 ? "bottom" : "top"
  }
  const side = sideFor(link)
  const attached = links.filter(item => (item.from === device.id || item.to === device.id) && sideFor(item) === side)
    .sort((a, b) => {
      const aPort = a.from === device.id ? a.fromPort : a.toPort
      const bPort = b.from === device.id ? b.fromPort : b.toPort
      return String(aPort ?? "").localeCompare(String(bPort ?? ""), undefined, { numeric: true }) || a.id.localeCompare(b.id)
    })
  const index = Math.max(0, attached.findIndex(item => item.id === link.id))
  const horizontal = side === "left" || side === "right"
  const offset = (index - (attached.length - 1) / 2) * (horizontal ? 26 : 58)
  const sign = side === "left" || side === "top" ? -1 : 1
  const x = device.x + (horizontal ? sign * 108 : offset)
  const y = device.y + (horizontal ? offset : sign * 72)
  const anchor = horizontal
    ? { x: device.x + sign * 70, y: device.y + Math.max(-36, Math.min(36, offset)) }
    : { x: device.x + Math.max(-58, Math.min(58, offset)), y: device.y + sign * 46 }
  const leader = horizontal
    ? `M ${anchor.x} ${anchor.y} H ${device.x + sign * 78} V ${y} H ${x - sign * 25}`
    : `M ${anchor.x} ${anchor.y} V ${device.y + sign * 54} H ${x} V ${y - sign * 9}`
  return { x, y, side, leader, anchor,
    exit: { x: x + (horizontal ? sign * 36 : 0), y: y + (horizontal ? 0 : sign * 20) } }
}

export function compactPortLabel(port?: string) {
  return String(port || "PORT 1").split(/\s+[·•]\s+/).pop()!
    .replace(/^Manual Port\s*/i, "M")
    .replace(/^TenGigabitEthernet/i, "Te")
    .replace(/^GigabitEthernet/i, "Gi")
    .replace(/^FastEthernet/i, "Fa")
    .replace(/^Ethernet/i, "Eth")
}
