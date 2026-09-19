import assert from "node:assert/strict"
import { readFile } from "node:fs/promises"
import { test } from "node:test"

const page = await readFile(
  new URL("../src/pages/ManualTopology.tsx", import.meta.url),
  "utf8",
)
const portMap = await readFile(
  new URL("../src/pages/DevicePortMap.tsx", import.meta.url),
  "utf8",
)
const routes = await readFile(
  new URL("../src/routes.tsx", import.meta.url),
  "utf8",
)
const sidebar = await readFile(
  new URL("../src/components/Sidebar.tsx", import.meta.url),
  "utf8",
)

test("manual topology keeps its permission-gated route and navigation entry", () => {
  assert.match(
    routes,
    /path: ['"]manual-topology['"][\s\S]*withPermission\(ManualTopology, ['"]topology:read['"]\)/,
  )
  assert.match(
    sidebar,
    /to: ['"]\/manual-topology['"], label: ['"]Manual Topology['"]/,
  )
})

test("manual topology renders the new real-data SVG editor contract", () => {
  assert.match(page, /getLatestManualTopologySnapshot/)
  assert.match(page, /listSNMPDevicesOptimized/)
  assert.match(page, /getSNMPInterfaces/)
  assert.match(page, /getSNMPTopology/)
  assert.match(page, /autoWorkspaceFromTopology/)
  assert.match(
    page,
    /createManualTopologySnapshot|updateManualTopologySnapshot/,
  )
  assert.match(page, /reconcileManualTopology/)
  assert.match(page, /setInterval\(syncAutomaticTopology, 30000\)/)
  assert.match(page, /view.*manual.*actual.*compare/s)
  assert.match(page, /MiniMap/)
  assert.match(page, /Search device\.\.\./)
  assert.doesNotMatch(page, /INTERNET \/ ISP|CORE SWITCH CS-01|Office PC/)
})

test("manual topology exposes the staged port-to-port connection workflow", () => {
  assert.match(page, /Connect workflow/)
  assert.match(page, /source.*port.*destination device.*port/s)
  assert.match(page, /Create & Save Link/)
  assert.match(page, /reconcileManualTopology/)
  assert.match(page, /fromIfIndex: sourceInterface\?\.ifIndex \?\? null/)
  assert.match(page, /toIfIndex: targetInterface\?\.ifIndex \?\? null/)
  assert.match(page, /Ports \/ Interfaces/)
  assert.match(page, /Physical Ports/)
  assert.match(page, /All Interfaces/)
  assert.match(page, /Search ports/)
  assert.match(page, /CONNECTING|CONNECT/)
  assert.match(page, /status: "VERIFYING"/)
  assert.match(page, /status === "VERIFIED"/)
  assert.match(page, /status === "UNKNOWN"/)
  assert.match(page, /manual_fallback/)
  assert.match(page, /previewPath/)
  assert.match(page, /Remove Bend/)
})

test("manual topology provides the enterprise command header and persistent panels", () => {
  assert.match(page, /workspace\.devices\.length/)
  assert.match(page, /workspace\.links\.length/)
  assert.match(page, /changes\.length/)
  assert.match(page, /view === "actual"/)
  assert.match(page, /Inspector/)
  assert.match(page, /OVERVIEW.*PORTS.*MONITORING/s)
  assert.match(page, /CONNECT DEVICES/)
  assert.match(page, /CREATE & VERIFY/)
  assert.match(page, /Actual topology refreshes automatically every 30 seconds/)
})

test("manual topology preserves complete port discovery and safe workspace removal", () => {
  assert.match(page, /PHYSICAL PORTS/)
  assert.match(page, /ALL INTERFACES/)
  assert.match(page, /manual.*physical port not discovered/s)
  assert.match(page, /ADD TO TOPOLOGY/)
  assert.match(page, /Remove From Topology/)
  assert.match(page, /updateDevice\(device\.backendId/)
  assert.match(page, /window\.setInterval\(syncAutomaticTopology, 30000\)/)
})

test("manual topology integrates the dedicated real-data device port map", () => {
  assert.match(routes, /manual-topology\/device\/:deviceId\/ports/)
  assert.match(routes, /DevicePortMap/)
  assert.match(page, /PORT MAP/)
  assert.match(page, /connectDevice/)
  assert.match(page, /connectPort/)
  assert.match(portMap, /getSNMPInterfaces/)
  assert.match(portMap, /getLatestInterfaces/)
  assert.match(portMap, /getLatestManualTopologySnapshot/)
  assert.match(portMap, /updateManualTopologySnapshot/)
  assert.match(portMap, /Device front panel/)
  assert.match(portMap, /CONNECTED DEVICE.*REMOTE PORT.*VERIFICATION/s)
  assert.match(portMap, /SFP|QSFP|TenGig|uplink/i)
  assert.match(portMap, /MANUAL.*selectedLink.*status/s)
  assert.match(portMap, /DISCONNECT/)
  assert.match(portMap, /manual-topology\?connectDevice/)
})

test("device port map keeps operational loading states and real interface classification", () => {
  assert.match(portMap, /LOADING DEVICE PORTS/)
  assert.match(portMap, /UNABLE TO LOAD PORTS/)
  assert.match(portMap, /setRetryToken/)
  assert.match(portMap, /REFRESHING PORT STATUS/)
  assert.match(portMap, /PHYSICAL PORTS|SFP \/ HIGH-SPEED UPLINK BAY/)
  assert.match(portMap, /naturalPortSort/)
  assert.match(portMap, /isLogical/)
  assert.match(portMap, /isManagement/)
  assert.match(portMap, /SFP \/ HIGH-SPEED UPLINK BAY/)
  assert.match(portMap, /Logical Interfaces \/ Not Physical Sockets/)
  assert.match(portMap, /aria-label=.*port\.name/s)
  assert.match(portMap, /Zoom in front panel/)
  assert.match(portMap, /Math\.max\(75/)
  assert.match(portMap, /Math\.min\(200/)
})

test("manual topology uses one shared inline device editor", () => {
  assert.match(page, /EDIT DEVICE/)
  assert.match(page, /SaveEditedDevice|saveEditedDevice/)
  assert.match(page, /MANUAL-ONLY/)
  assert.match(page, /BACKEND-LINKED/)
  assert.match(page, /editableDeviceTypes/)
  assert.match(page, /list="manual-device-types"/)
  assert.match(page, /Type a device category to update its icon/)
  assert.doesNotMatch(page, /READ ONLY: discovered device type/)
  assert.match(page, /changing management IP can affect.*monitoring/s)
  assert.match(page, /inventory-derived identity/)
  assert.match(page, /Device name is required/)
  assert.match(page, /Invalid IP address/)
  assert.match(page, /Invalid MAC address/)
  assert.match(page, /Failed to update device/)
  assert.match(page, /SAVING\.\.\./)
  assert.match(page, /if \(connectMode\) resetConnection\(\)/)
})

test("manual topology edit persistence preserves identity and topology metadata", () => {
  assert.match(page, /const nextDevice: Device = \{\s*\.\.\.device/s)
  assert.match(page, /devices: workspace\.devices\.map/)
  assert.match(page, /topology_metadata/)
  assert.match(page, /description\?: string/)
  assert.match(page, /toneFor\(/)
})

test("manual topology classifies realistic device visuals and enforces physical occupancy", () => {
  assert.match(page, /classifyDevice/)
  assert.match(page, /CORE_SWITCH|ACCESS_POINT|GENERIC_DEVICE/)
  assert.match(
    page,
    /function glyph\(type: string, name\?: string, vendor\?: string, model\?: string\)/,
  )
  assert.match(page, /Logical interfaces cannot be used/)
  assert.match(page, /getPortOccupancy/)
  assert.match(page, /Port already in use/)
  assert.match(page, /sourceOccupancy|targetOccupancy/)
  assert.match(page, /portView === "all" \|\| !isLogicalPort\(port\)/)
  assert.match(page, /selectedPortSummary/)
  assert.match(page, /evidence unavailable/)
})

test("manual topology preserves edge-anchored links and accepted real changes", () => {
  assert.match(page, /const linkEndpoints = \(link: Link\)/)
  assert.match(page, /routingPoints \?\? \[\]/)
  assert.match(page, /action === "accept_real_change" && result\.payload/)
  assert.match(
    page,
    /localStorage\.setItem\(STORAGE_KEY, JSON\.stringify\(next\)\)/,
  )
})

test("manual topology provides production viewport controls without topology writes", () => {
  assert.match(page, /VIEWPORT_STORAGE_KEY/)
  assert.match(page, /Math\.min\(3, Math\.max\(0\.25, value\)\)/)
  assert.match(page, /zoomAtClientPoint/)
  assert.match(page, /event\.ctrlKey.*event\.metaKey/s)
  assert.match(page, /Fit visible topology/)
  assert.match(page, /fitToView/)
  assert.match(page, /focusDevice\(device\)/)
  assert.match(page, /setPan\(\{[\s\S]*CANVAS\.width \/ 2 - point\.x \* zoom/)
  assert.match(page, /event\.key === "0"/)
  assert.match(page, /event\.key\.toLowerCase\(\) === "f"/)
})

test("manual topology renders deterministic port sockets and link endpoint inspection", () => {
  assert.match(page, /const linkEndpoints = \(link: Link\)/)
  assert.match(page, /setHoveredLinkId/)
  assert.match(page, /PORT UNKNOWN/)
  assert.match(page, /MANUAL\)/)
  assert.match(page, /setHoveredLinkId/)
  assert.match(page, /endpoints\.source(?:\.exit)?\.x/)
  assert.match(page, /endpoints\.target(?:\.exit)?\.x/)
  assert.match(page, /SOURCE PORT/)
  assert.match(page, /TARGET PORT/)
  assert.match(page, /DELETE MANUAL LINK/)
  assert.match(page, /VIEW SOURCE PORT/)
  assert.match(page, /port=\$\{encodeURIComponent\(selectedLink\.fromPort/)
  assert.match(page, /setSelectedLinkId\(link\.id\)/)
})

test("manual topology provides device hover details and smooth drag handling", () => {
  assert.match(page, /hoveredDeviceId/)
  assert.match(page, /TOTAL PORTS/)
  assert.match(page, /UP PORTS/)
  assert.match(page, /CONNECTED/)
  assert.match(page, /MAC/)
  assert.match(page, /foreignObject/)
  assert.match(page, /setPointerCapture/)
  assert.match(page, /requestAnimationFrame/)
  assert.match(page, /Keep pointer movement continuous/)
  assert.match(page, /Math\.round\(device\.x \/ 20\) \* 20/)
})

test("manual topology derives device icons from names and metadata", () => {
  assert.match(page, /hints\.includes\("switch"\)/)
  assert.match(page, /hints\.includes\("router"\)/)
  assert.match(page, /hints\.includes\("firewall"\)/)
  assert.match(page, /hints\.includes\("nvr"\)/)
  assert.match(page, /\(\^\|\\s\)nr\(\\s\|\[-_\]\|\$\)/)
  assert.match(page, /hints\.includes\("access point"\)/)
  assert.match(page, /hints\.includes\("storage"\)/)
})

test("manual topology overlays authoritative device health without creating alerts or snapshots", () => {
  assert.match(page, /getOverview\(\)/)
  assert.match(page, /deviceHealth/)
  assert.match(page, /device\.backendId != null/)
  assert.match(page, /setInterval\(syncDeviceHealth, 10000\)/)
  assert.match(page, /healthStatusFor\(device\)/)
  assert.match(page, /healthColorFor\(device\)/)
  assert.match(page, /setDeviceHealth\(next\)/)
  assert.match(page, /\.catch\(\(\) => undefined\)/)
  assert.doesNotMatch(page, /create.*Alert|post.*alert/i)
})

test("manual topology reserves red for offline rendering and preserves configured tones", () => {
  assert.match(page, /healthStatusFor\(device\) === "offline" \? "#d9646a" : device\.tone/)
  assert.match(page, /deviceIllustration\(device\.type, renderedToneFor\(device\)\)/)
  assert.match(page, /fill=\{healthColorFor\(device\)\}/)
  assert.match(page, /\["Firewall", "Router", "Switch", "Server", "Wireless", "Generic Device"\]/)
  assert.match(page, /status: "manual"/)
  assert.match(page, /tone: toneFor\(type, workspace\.devices\.length\)/)
  assert.doesNotMatch(page, /const palette\s*=\s*\[[^\]]*#d9646a/s)
})

test("manual connections verify live physical ports and expose mismatch details", () => {
  assert.match(page, /WRONG PHYSICAL CONNECTION/)
  assert.match(page, /PORT_MISMATCH/)
  assert.match(page, /selected ports do not match the live physical connection/)
  assert.match(page, /SELECTED:/)
  assert.match(page, /ACTUAL:/)
  assert.match(page, /Physical connectivity verified/)
  assert.match(page, /Wrong physical connection/)
  assert.match(page, /evidence_available/)
})
