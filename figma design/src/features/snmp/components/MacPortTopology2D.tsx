import { useMemo, useRef, useState } from "react"

type PortGroup = {
  port?: string | number
  if_index?: string | number
  classification?: string
  mac_count?: number
  macs?: string[]
  vlans?: Array<string | number>
  ip_addresses?: string[]
  ips?: string[]
}

export default function MacPortTopology2D({ groups }: { groups: PortGroup[] }) {
  const [selectedPort, setSelectedPort] = useState<string | null>(null)
  const [zoom, setZoom] = useState(1)
  const [position, setPosition] = useState({ x: 0, y: 0 })
  const drag = useRef<{ x: number y: number } | null>(null)
  const visibleGroups = useMemo(
    () =>
      groups.filter(
        (group) => group.port !== undefined || group.if_index !== undefined,
      ),
    [groups],
  )
  if (!visibleGroups.length) return null

  return (
    <div
      className="p-4 sm:p-5"
      style={{ borderBottom: "1px solid rgba(0,212,255,0.08)" }}
    >
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <div>
          <div
            className="font-display text-xs font-bold tracking-[.16em]"
            style={{ color: "#00d4ff" }}
          >
            2D PORT TOPOLOGY
          </div>
          <div
            className="mt-1 font-mono text-[9px] uppercase tracking-wider"
            style={{ color: "#667799" }}
          >
            Learned forwarding relationships
          </div>
        </div>
        <div className="font-mono text-[10px]" style={{ color: "#8899bb" }}>
          MAC <span style={{ color: "#00d4ff" }}>→</span> PORT{" "}
          <span style={{ color: "#00d4ff" }}>→</span> IP / VLAN · SELECT A PORT
        </div>
      </div>
      <div
        className="relative overflow-hidden rounded-xl"
        onPointerDown={(event) => {
          if ((event.target as HTMLElement).closest("button")) return
          drag.current = { x: event.clientX, y: event.clientY }
          event.currentTarget.setPointerCapture(event.pointerId)
        }}
        onPointerMove={(event) => {
          if (!drag.current) return
          const dx = event.clientX - drag.current.x
          const dy = event.clientY - drag.current.y
          setPosition((value) => ({ x: value.x + dx, y: value.y + dy }))
          drag.current = { x: event.clientX, y: event.clientY }
        }}
        onPointerUp={(event) => {
          drag.current = null
          event.currentTarget.releasePointerCapture(event.pointerId)
        }}
        onPointerCancel={() => {
          drag.current = null
        }}
        style={{
          height: 430,
          backgroundImage:
            "linear-gradient(rgba(0,212,255,.035) 1px, transparent 1px), linear-gradient(90deg, rgba(0,212,255,.035) 1px, transparent 1px), radial-gradient(circle at 50% 42%, rgba(0,212,255,.13), transparent 32%), linear-gradient(145deg, #061426, #020711 72%)",
          backgroundSize: "32px 32px, 32px 32px, auto, auto",
          border: "1px solid rgba(0,212,255,.16)",
          cursor: drag.current ? "grabbing" : "grab",
        }}
      >
        <div
          className="absolute top-3 right-3 z-30 flex overflow-hidden rounded-md"
          style={{
            background: "rgba(2,8,18,.9)",
            border: "1px solid rgba(0,212,255,.2)",
          }}
        >
          <button
            type="button"
            onClick={() =>
              setZoom((value) => Math.min(1.8, +(value + 0.1).toFixed(1)))
            }
            className="px-3 py-1 font-mono text-sm"
            style={{ color: "#00d4ff" }}
          >
            +
          </button>
          <button
            type="button"
            onClick={() =>
              setZoom((value) => Math.max(0.55, +(value - 0.1).toFixed(1)))
            }
            className="px-3 py-1 font-mono text-sm border-l border-cyan-400/10"
            style={{ color: "#00d4ff" }}
          >
            −
          </button>
          <button
            type="button"
            onClick={() => {
              setZoom(1)
              setPosition({ x: 0, y: 0 })
            }}
            className="px-2 py-1 font-mono text-[9px] border-l border-cyan-400/10"
            style={{ color: "#8899bb" }}
          >
            RESET
          </button>
        </div>
        <div
          className="absolute inset-0"
          style={{
            transform: `translate(${position.x}px, ${position.y}px) scale(${1.05 * zoom})`,
            transformOrigin: "center center",
          }}
        >
          <div
            className="absolute left-1/2 top-1/2 rounded-full"
            style={{
              width: 176,
              height: 176,
              transform: "translate(-50%, -50%)",
              background:
                "radial-gradient(circle, rgba(0,212,255,.3), rgba(0,50,90,.8) 56%, rgba(0,212,255,.08))",
              border: "2px solid rgba(0,212,255,.65)",
              boxShadow:
                "0 0 45px rgba(0,212,255,.35), inset 0 0 35px rgba(0,212,255,.2)",
            }}
          />
          <div
            className="absolute left-1/2 top-1/2 font-display font-bold text-sm tracking-wider"
            style={{
              transform: "translate(-50%, -50%)",
              color: "#c8d8ee",
              textShadow: "0 0 12px #00d4ff",
              whiteSpace: "nowrap",
            }}
          >
            CORE SWITCH
          </div>
          <div
            className="absolute left-1/2 top-1/2 font-mono text-[10px]"
            style={{
              transform: "translate(-50%, 12px)",
              color: "#00ff88",
              whiteSpace: "nowrap",
            }}
          >
            LIVE MAC TABLE
          </div>
          {visibleGroups.map((group, index) => {
            const port = String(group.port ?? group.if_index)
            const angle =
              (index / visibleGroups.length) * Math.PI * 2 - Math.PI / 2
            const radiusX = 42
            const radiusY = 40
            const x = 50 + Math.cos(angle) * radiusX
            const y = 50 + Math.sin(angle) * radiusY
            const active = selectedPort === port
            const ips = group.ip_addresses || group.ips || []
            const color =
              group.classification === "ENDPOINT"
                ? "#00ff88"
                : group.classification === "UPLINK/TRUNK"
                  ? "#a78bfa"
                  : "#ffaa00"
            return (
              <div key={`${port}-${index}`}>
                <div
                  className="absolute left-1/2 top-1/2 origin-left"
                  style={{
                    width: `${Math.hypot((x - 50) * 2.1, (y - 50) * 1.8)}%`,
                    transform: `rotate(${angle}rad)`,
                    borderTop: `2px ${active ? "solid" : "dashed"} ${color}`,
                    opacity: active ? 1 : 0.62,
                    boxShadow: active ? `0 0 10px ${color}` : undefined,
                  }}
                />
                <button
                  type="button"
                  aria-label={`Port ${port}, ${group.mac_count ?? group.macs?.length ?? 0} MAC addresses, ${ips.length} IP addresses`}
                  onClick={() => setSelectedPort(active ? null : port)}
                  className="absolute rounded-lg text-left transition-transform hover:scale-105"
                  style={{
                    left: `${x}%`,
                    top: `${y}%`,
                    transform: "translate(-50%, -50%)",
                    minWidth: 156,
                    padding: "10px 12px",
                    color: "#c8d8ee",
                    background:
                      "linear-gradient(145deg, rgba(8,25,55,.98), rgba(2,8,18,.98))",
                    border: `1px solid ${active ? color : `${color}88`}`,
                    boxShadow: `0 0 ${active ? 24 : 10}px ${color}55`,
                    cursor: "pointer",
                  }}
                >
                  <div className="flex items-center justify-between gap-3">
                    <div
                      className="font-display text-[10px] font-bold tracking-wider"
                      style={{ color }}
                    >
                      PORT {port}
                    </div>
                    <span
                      className="h-1.5 w-1.5 rounded-full"
                      style={{
                        background: color,
                        boxShadow: `0 0 7px ${color}`,
                      }}
                    />
                  </div>
                  <div
                    className="mt-1 font-mono text-[9px]"
                    style={{ color: "#8899bb" }}
                  >
                    {group.mac_count ?? group.macs?.length ?? 0} MACs{" "}
                    <span style={{ color: "#334966" }}>·</span> {ips.length} IPs
                  </div>
                  <div
                    className="font-mono text-[9px]"
                    style={{ color: "#667799" }}
                  >
                    VLAN {group.vlans?.join(", ") || "UNKNOWN"}
                  </div>
                </button>
                {active && (
                  <div
                    className="absolute z-20 rounded-lg p-2 font-mono text-[9px]"
                    style={{
                      left: `${Math.min(80, Math.max(8, x - 8))}%`,
                      top: `${Math.min(84, y + 10)}%`,
                      maxWidth: 220,
                      color: "#c8d8ee",
                      background: "rgba(2,8,18,.96)",
                      border: `1px solid ${color}77`,
                      boxShadow: `0 0 18px ${color}33`,
                    }}
                  >
                    <div style={{ color }}>PORT {port} DETAILS</div>
                    <div>MACs: {group.macs?.join(", ") || "UNKNOWN"}</div>
                    <div>IPs: {ips.join(", ") || "UNKNOWN"}</div>
                    <div>VLANs: {group.vlans?.join(", ") || "UNKNOWN"}</div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
        <div
          className="absolute bottom-3 left-3 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[9px]"
          style={{ color: "#667799" }}
        >
          <span>DRAG TO PAN</span>
          <span>+ / − ZOOM</span>
          <span>
            <i
              className="mr-1 inline-block h-1.5 w-1.5 rounded-full"
              style={{ background: "#00ff88" }}
            />
            ENDPOINT
          </span>
          <span>
            <i
              className="mr-1 inline-block h-1.5 w-1.5 rounded-full"
              style={{ background: "#a78bfa" }}
            />
            UPLINK
          </span>
        </div>
      </div>
    </div>
  )
}
