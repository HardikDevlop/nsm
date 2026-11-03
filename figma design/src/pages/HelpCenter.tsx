import { useEffect, useMemo, useState } from 'react'
import GlassCard from '../components/GlassCard'

/* =====================================================================
   Types
   ===================================================================== */

type Section = {
  title: string
  body?: string
  steps?: string[]
  warning?: string
  faqs?: [string, string][]
}

type Category = 'Monitoring' | 'Devices' | 'Alerts & Reports' | 'Administration'

type Guide = {
  name: string
  category: Category
  icon: string
  description?: string
  pdf?: string
  downloadName?: string
}

/* =====================================================================
   Guide list
   ===================================================================== */

const pdf = (slug: string, file: string) => ({
  pdf: `/help/${slug}-user-guide.pdf`,
  downloadName: `AgniGate_NMS_${file}_User_Guide.pdf`,
})

const guides: Guide[] = [
  { name: 'Overview', category: 'Monitoring', description: 'Dashboard metrics, device status, system health and monitoring overview.', ...pdf('overview', 'Overview'), icon: 'M3 3v18h18M7 16v-5m5 5V7m5 9v-8' },
  { name: 'Topology', category: 'Monitoring', description: 'Network topology, devices, connections, ports and topology management.', ...pdf('topology', 'Topology'), icon: 'M12 3v18M3 12h18M5 5l14 14M19 5L5 19' },
  { name: 'IP Scan', category: 'Devices', description: 'Network discovery, ICMP/SNMP scanning, stored devices and inventory management.', ...pdf('ip-scan', 'IP_Scan'), icon: 'M8.1 16.4a5.5 5.5 0 017.8 0M12 20h.01m-7.1-7.1a10 10 0 0114.2 0M1.4 9.4a15 15 0 0121.2 0' },
  { name: 'All Devices', category: 'Devices', description: 'Saved device inventory, status, connectivity and monitoring information.', ...pdf('all-devices', 'All_Devices'), icon: 'M4 6a2 2 0 012-2h12a2 2 0 012 2v12a2 2 0 01-2 2H6a2 2 0 01-2-2V6z' },
  { name: 'Windows Devices', category: 'Devices', description: 'Windows PC and Server onboarding, WinRM HTTPS monitoring, diagnostics and saved metrics.', ...pdf('windows-devices', 'Windows_Devices'), icon: 'M4 5h16v14H4zM8 9h8M8 13h5' },
  { name: 'SNMP Devices', category: 'Devices', description: 'SNMP device onboarding, discovery, inventory, credentials and monitoring modules.', ...pdf('snmp-devices', 'SNMP_Devices'), icon: 'M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6z' },
  { name: 'Device Monitoring', category: 'Monitoring', description: 'ICMP availability, latency, packet loss and monitoring history.', ...pdf('device-monitoring', 'Device_Monitoring'), icon: 'M9 19V9m6 10V5m-9 14v-6' },
  { name: 'Packet Analysis', category: 'Monitoring', description: 'Interface telemetry, device metrics and alert-derived traffic visualizations.', ...pdf('packet-analysis', 'Packet_Analysis'), icon: 'M6 3h8l4 4v14H6zM9 12h6M9 16h4' },
  { name: 'APM Service Health', category: 'Monitoring', icon: 'M4 19h16M6 16v-5m4 5V7m4 9v-3m4 3V4' },
  { name: 'Linux Server Monitoring', category: 'Devices', description: 'SNMPv3 Linux metrics, security events, thresholds and short-term history.', ...pdf('linux-server-monitoring', 'Linux_Server_Monitoring'), icon: 'M4 5h16v14H4zM8 9h8M8 13h5' },
  { name: 'Report Center', category: 'Alerts & Reports', description: 'Operational reports, trends, availability, SLA summaries and scheduled report files.', ...pdf('report-center', 'Report_Center'), icon: 'M4 5h16v14H4zM7 9h10M7 13h6M7 17h4' },
  { name: 'Server Monitor', category: 'Devices', icon: 'M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2' },
  { name: 'Remote Access', category: 'Devices', description: 'Authorized SSH and Telnet terminal sessions, connection testing, host-key trust and session history.', ...pdf('remote-access', 'Remote_Access'), icon: 'M4 6h16M7 10v8m5-8v8m5-8v8' },
  { name: 'Alert Management', category: 'Alerts & Reports', description: 'Review, filter, acknowledge, resolve and manage device and monitoring alerts.', ...pdf('alert-management', 'Alert_Management'), icon: 'M12 9v2m0 4h.01M4 19h16L13.7 4.5a2 2 0 00-3.4 0L4 19z' },
  { name: 'Events', category: 'Alerts & Reports', description: 'Operational event history, device associations, search, pagination and event management.', ...pdf('events', 'Events'), icon: 'M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7H3v12a2 2 0 002 2z' },
  { name: 'Syslog Management', category: 'Alerts & Reports', icon: 'M4 5h16v14H4zM8 9h8M8 13h8M8 17h5' },
  { name: 'Notifications', category: 'Alerts & Reports', description: 'Notification records, alert associations, delivery states, permissions and email delivery limitations.', ...pdf('notifications', 'Notifications'), icon: 'M18 8a6 6 0 00-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4' },
  { name: 'Monitoring Jobs', category: 'Monitoring', icon: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z' },
  { name: 'Role Management', category: 'Administration', icon: 'M12 3l8 4v5c0 5-3.5 8-8 9-4.5-1-8-4-8-9V7z' },
  { name: 'User Management', category: 'Administration', icon: 'M12 4a4 4 0 110 8 4 4 0 010-8M4 21a8 8 0 0116 0' },
  { name: 'Organizations', category: 'Administration', icon: 'M5 21V5a2 2 0 012-2h10a2 2 0 012 2v16M9 7h1m4 0h1m-6 4h1m4 0h1' },
  { name: 'Sites', category: 'Administration', icon: 'M12 21s7-5.2 7-11a7 7 0 10-14 0c0 5.8 7 11 7 11zM12 13a3 3 0 100-6 3 3 0 000 6z' },
  { name: 'Vendors', category: 'Administration', icon: 'M4 20V6h16v14M8 10h8M8 14h8' },
  { name: 'Device Types', category: 'Administration', icon: 'M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6z' },
  { name: 'Device Credentials', category: 'Administration', icon: 'M15 7a2 2 0 112 2m4 0a6 6 0 01-7.7 5.7L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.6l6-6A6 6 0 1121 9z' },
  { name: 'Audit Logs', category: 'Administration', icon: 'M7 3h10v18H7zM10 8h4m-4 4h4m-4 4h3' },
]

const categories: ('All' | Category)[] = ['All', 'Monitoring', 'Devices', 'Alerts & Reports', 'Administration']

/* =====================================================================
   Guide content
   ===================================================================== */

const overviewSections: Section[] = [
  { title: 'Introduction', body: 'The Overview dashboard is the starting point for understanding Network Operations. Use it to check device availability, traffic, alerts, and monitoring activity using information already collected by NMS. Opening Overview does not start a new network scan.' },
  { title: 'Getting started', steps: ['Sign in to NMS and select Overview from the left menu.', 'At the top-right, select 1H, 6H, 12H, 24H, or 7D to change the displayed time period.', 'Select REFRESH to update the dashboard information. The page also refreshes automatically while visible.'] },
  { title: 'Dashboard summary cards', body: 'Total Devices: the number of devices in your accessible inventory. Online / Offline: devices currently shown as reachable or unreachable. SNMP Enabled: devices configured for SNMP monitoring. SNMP Failed: failed SNMP polling attempts in the selected period. Critical / Warning Alerts: important alerts requiring review. Interfaces Down: network interfaces whose latest recorded status is down.' },
  { title: 'Main dashboard sections', body: 'Live Traffic shows RX incoming traffic and TX outgoing traffic from recent stored measurements. Network Health shows availability, polling, interface health, SNMP setup, overall health, and traffic indicators. Status Share shows how many devices are online, offline, or in another health state. Network Traffic shows incoming and outgoing traffic over the selected period. Top Devices by Traffic helps identify devices carrying the most traffic. Device Type Map / Device Types shows how devices are grouped by recorded type. Alerts shows alerts by severity; open Alert Management to investigate important alerts.' },
  { title: 'Monitoring indicators and activity', body: 'Interfaces shows Total, Up, and Down latest recorded interface states; Errors and Drops indicate interface problems worth reviewing. SNMP Monitoring shows successful, failed, unsupported, and other polling attempts. Poll Success measures success among successful and failed polling attempts; other categories are excluded. System Vitals shows Availability, Poll Success, Avg CPU, and Avg Memory for the selected NMS/Linux server, not an average of all network devices. Worker & Job Health shows whether the SNMP polling engine and real-time monitor are running, plus job and failure information. Historical Correlation shows whether alerts match recorded outage or performance events around the same time. Network Information summarizes discovered LLDP/CDP neighbors, VLANs, routes, ARP, MAC records, and topology nodes. Recent Devices / Activity shows device names, IP addresses, last known status, and latest polling time.' },
  { title: 'How to use Overview', steps: ['Open Overview from the left navigation menu.', 'Check Online and Offline counts, Critical Alerts, Warning Alerts, Interfaces Down, SNMP Failed, and Poll Success.', 'Choose a time period to review traffic, polling, and alert information for that period.', 'Review Network Health, Status Share, Network Information, and Recent Devices / Activity.', 'Review unusual traffic or alert changes, then open detailed pages to investigate anything unusual.', 'Use REFRESH when values appear old. If a device appears Offline, open its detailed monitoring page before taking corrective action.'] },
  { title: 'Daily-use checklist', steps: ['Check Online and Offline device counts.', 'Review Critical Alerts, Warning Alerts, and Interfaces Down.', 'Check SNMP Failed and Poll Success.', 'Review network traffic for unusual increases or drops.', 'Check whether monitoring workers show Running.', 'Open detailed pages to investigate anything unusual.'] },
  { title: 'Important warnings and precautions', warning: 'A dashboard value can be delayed if device polling has not updated yet. A high number of down interfaces needs investigation; it does not automatically mean every connected device is offline. Do not assume an Offline device is permanently faulty, treat Stale information as a confirmed outage, or treat N/A as zero. Do not delete devices or change monitoring settings because a dashboard card shows a warning; seek administrator approval and investigate first. Overview does not run discovery, device scans, scheduled reports, or emails.' },
  { title: 'Permissions and access', body: 'The devices and information shown depend on the user account’s accessible inventory and site visibility. If access is denied, contact an administrator to verify Overview access. Users may not see the same devices.' },
  { title: 'Troubleshooting', body: 'No devices shown: check whether devices have been added and whether your account can view the relevant site. Traffic chart empty: select a different time period and check whether interface monitoring has collected data. Values look old: press REFRESH, then check monitoring-job status and device details. Access denied: contact your administrator to verify Overview access. If a card opens an error page, report the affected card to the administrator; some navigation targets still require verification.' },
  { title: 'Frequently asked questions', faqs: [['Does REFRESH scan the network?', 'No. It requests updated Overview information already stored by NMS.'], ['Does changing 12H to 24H delete anything?', 'No. It changes only the displayed time range.'], ['Can I stop monitoring from Overview?', 'No stop/restart control was found on this page.'], ['Are all users shown the same devices?', 'Not necessarily. Visibility depends on access permissions.']] },
]

const topologySections: Section[] = [
  { title: 'Introduction', body: 'Network Topology is a visual workspace for viewing network devices, checking their latest reported status, understanding available connections, and safely organizing a map. Use it to find devices by name or IP, inspect details and ports, compare saved and discovered topology evidence, and create diagram links. Diagram links organize the NMS map; they do not physically connect network equipment.' },
  { title: 'Workspace overview', body: 'The top toolbar contains topology actions and view controls. The left Devices panel contains ON CANVAS, AVAILABLE, and MANUAL tabs, type filters, and device search. The center dotted canvas is the map where devices can be selected and manually repositioned. The right Inspector panel shows overview, ports, and monitoring information for the selected item.' },
  { title: 'Topology modes', body: 'MANUAL is the editable, saved map where devices can be placed, arranged, and linked. ACTUAL shows network connections inferred from available discovery data and may be incomplete when devices do not provide enough information. COMPARE highlights differences between the saved manual map and discovered evidence; review differences before accepting changes. These modes represent map views and available evidence, not a guarantee that every physical connection is known.' },
  { title: 'Find a device and check its status', steps: ['Open the ON CANVAS or AVAILABLE tab in the Devices panel.', 'Enter a device name or IP in Search devices.', 'Select the device or choose FOCUS to center it on the map.', 'Choose VIEW to inspect more details, or PORT MAP to inspect ports.', 'Hover over a device on the map to see its information card where supported.'], body: 'Online or Offline is based on the latest available monitoring evidence. If the last update is old, confirm the current status in Device Monitoring before taking action.' },
  { title: 'Device information and actions', body: 'FOCUS centers and zooms to a device. VIEW shows device information. EDIT changes device information; for an inventory-linked device, saving may update the NMS inventory record, so use it only when authorized. PORT MAP opens the device port view. The inspector can show overview, ports, and monitoring information for the selected item.' },
  { title: 'Toolbar controls', body: '+ DEVICE opens the symbols/device palette; a manual symbol is a map item, not a newly monitored NMS device. CONNECT starts the connection workflow. AUTO LAYOUT automatically arranges devices on the saved map. FIT adjusts the map view. SNAP ON/OFF aligns moved devices to the grid. UNDO/REDO reverses or restores local workspace changes; persistence after undo/redo still needs live verification. EXPORT downloads a topology image. SHOW PORTS toggles port labels. FULLSCREEN enlarges the map view and may provide EXIT FULL to return.' },
  { title: 'Canvas controls, polling, and saved status', body: 'Use the + and − controls, zoom slider, mouse wheel, or FIT to adjust the map view; zoom does not change devices or their network configuration. HIDE SIDEBAR temporarily removes the side panel; SHOW SIDEBAR or UNHIDE brings it back. Use All links and related filters to show selected connection states; these filters do not delete data. The POLL selector controls how often the page checks topology differences; shorter intervals can cause repeated collection requests. The map is automatically saved after changes; wait for the Saved indicator before leaving.' },
  { title: 'Create and review diagram links', steps: ['Select CONNECT to start the connection workflow.', 'Choose a source device and port, then a different target device and port.', 'Review both endpoints before selecting CREATE & SAVE LINK.', 'Select CANCEL to leave without creating a link.', 'When a link is selected, available actions may include + BEND, RESET ROUTE, and DELETE.'], warning: 'A manual link represents a connection on the NMS map. It does not connect cables, configure switch ports, or change a router. Deleting a diagram link removes it from the saved map, not the physical network.' },
  { title: 'Port Map', body: 'Select PORT MAP for a device to review its ports. Use ALL, USED, FREE, UP, DOWN, and ISSUES filters. Click a port for details or select VIEW LINK to inspect a mapped connection. CONNECT from Port Map returns to the topology connection workflow. DISCONNECT removes a saved diagram link after confirmation; it does not disable the physical interface. Available port data may be incomplete when a device does not return complete interface information; manual or fallback ports are not proof of a real connection.' },
  { title: 'Device management warnings', warning: 'Do not use EDIT unless you are permitted to change device information. Remove From Topology removes a device and its links from the visual workspace; it does not delete that device from monitored NMS inventory. Do not use Remove From Topology, DELETE, or DISCONNECT without checking the selected map item. Disconnecting a topology link does not disable the physical network port.' },
  { title: 'Autosave and polling precautions', body: 'The map is automatically saved after changes. Wait for the Saved indicator before leaving. The POLL interval checks topology differences; leave the interval unchanged unless an authorized administrator asks you to adjust it, because shorter intervals can cause repeated collection requests. Review differences before accepting discovered changes and do not assume a drawn link is a verified physical connection.' },
  { title: 'Step-by-step daily usage', steps: ['Open Topology from the left navigation menu.', 'Choose MANUAL, ACTUAL, or COMPARE according to whether you need the saved map, discovered evidence, or differences.', 'Search for a device, select it, and use FOCUS, VIEW, or PORT MAP as needed.', 'Use zoom, FIT, or FULLSCREEN to inspect the map without changing the network.', 'Review device status and the last available monitoring evidence before acting.', 'For a diagram link, verify two different devices and valid ports before CREATE & SAVE LINK.', 'Wait for Saved after moving, adding, or removing map items before leaving.'] },
  { title: 'Daily-use checklist', steps: ['Check the selected mode and map counts.', 'Review device status timestamps before treating a device as Offline.', 'Inspect ports and available evidence before creating or accepting links.', 'Use COMPARE to review differences before accepting discovered changes.', 'Keep the POLL interval unchanged unless authorized.', 'Confirm Saved after map changes.', 'Use EDIT, DELETE, DISCONNECT, and Remove From Topology only after checking the selected item and permissions.'] },
  { title: 'Permissions and access', body: 'Viewing the map and changing device inventory require different permissions. If you cannot edit a device or create a link, check with the NMS administrator. Role-specific errors, live discovery results, and some permission-specific behavior require verification in the deployed UI.' },
  { title: 'Troubleshooting', body: 'Why is a device Offline? The latest monitoring evidence indicates it was unreachable; check when that status was last updated. Why are ports missing? The device may not have returned complete interface data. Why can changes disappear? Check the Saved indicator and any error message before repeating a change. What if you cannot create a link? Check that two different devices and valid, unused physical ports are selected. Contact the NMS administrator before repeating a potentially destructive action.' },
  { title: 'Frequently asked questions', faqs: [['Does fullscreen change the network?', 'No. It only enlarges the map view.'], ['Why are some ports missing?', 'The device may not have returned complete interface data. Manual or fallback ports are not proof of a real connection.'], ['Why can I open Topology but not edit a device?', 'Viewing the map and changing device inventory require different permissions.'], ['What if I cannot create a link?', 'Check that two different devices and valid, unused physical ports are selected.'], ['What if changes disappear?', 'Check the save indicator and any error message. Contact the NMS administrator before repeating a potentially destructive action.']] },
]

const ipScanSections: Section[] = [
  { title: 'Introduction', body: 'IP Scan checks an approved IP address or range, finds reachable hosts, shows basic device details, and lets users add selected devices to NMS inventory. Use it for authorized network discovery and inventory review.' },
  { title: 'Screen overview', body: 'The DEVICES summary card shows the number of saved devices and opens the saved-device view. ONLINE shows saved devices currently marked online. OFFLINE shows saved devices not marked online. OPEN ALERTS navigates to Alert Management. The page also contains discovery controls, Discovered Devices, a saved-device Network Topology view, Stored Devices, and Device Management actions.' },
  { title: 'Discovery configuration', body: 'Discovery target accepts one IPv4 address, a dash-separated range, comma-separated IP addresses, or CIDR from /24 through /32. The maximum is 255 IP addresses. Choose ICMP for ping-based reachability. The SNMP control opens a separate SNMP discovery dialog; it is not simply a second checkbox.' },
  { title: 'Step-by-step discovery workflow', steps: ['Open IP Scan from the sidebar.', 'Enter an authorized target in Discovery target.', 'Choose ICMP, or open the separate SNMP discovery dialog.', 'Click DISCOVER DEVICES and wait for streamed results and progress. The button shows a running state while the scan is active.', 'Review the Discovered Devices section.', 'Use + Add for one new device, or Store all (N new) to save all new results.'] },
  { title: 'Discovery results', body: 'Results can include hostname, IP address, MAC address, status, and available SNMP/enrichment details. + Add saves one result; ✓ Stored means the IP is already in inventory. Scan results are temporary until explicitly saved. Existing active IPs may be updated rather than duplicated, and a matching soft-deleted record may be restored.' },
  { title: 'Network Topology', body: 'The gateway-style diagram shows saved inventory devices, not unsaved discovery results. Hover over a device to inspect available information. While this page is visible, its topology performs automatic ICMP checks about every 15 seconds; this is separate from a manual discovery scan. This page-level saved-device visualization is different from the main Topology module, which is the broader topology workspace for manual maps, discovered connections, comparisons, ports, and diagram links.' },
  { title: 'Stored Devices', body: 'Stored Devices initially shows up to five entries. Use Show all N devices or Show less to expand or collapse the list. Click Details to open the selected device monitoring page. “Ready for monitoring” does not prove that live monitoring has started; confirm actual monitoring in Device Monitoring.' },
  { title: 'Device Management', body: '+ ADD DEVICE opens a form for organization, site, hostname, IP, MAC, model, serial number, and firmware. Create device saves to inventory; Cancel closes without saving. + Org and + Site can create an organization or site from the add-device workflow when permitted. Details opens device monitoring details. Edit changes saved hostname, IP, MAC, model, serial, firmware, or site; Save commits changes and Cancel discards them. Checkboxes select devices for bulk deletion. Delete removes one saved device after confirmation. DELETE SELECTED removes checked saved devices after confirmation. DELETE ALL removes all devices in the page’s managed inventory scope after confirmation.' },
  { title: 'Permissions and access', body: 'View IP Scan page: isp:read. Run discovery: discovery:execute is checked by the frontend; backend enforcement requires separate live verification. View devices: devices:read. Add: devices:create. Edit: devices:update. Delete: devices:delete. Create organization: organizations:create. Create site: sites:create.' },
  { title: 'Recommended safe workflow', steps: ['Confirm the subnet and obtain authorization before scanning.', 'Start with a small target range, especially on a live network.', 'Review discovered names and IP addresses; reachability alone does not establish device identity.', 'Store only approved devices and verify details after saving.', 'Use individual Edit and Delete carefully; obtain explicit approval before bulk deletion.', 'Confirm actual monitoring separately after saving devices.'] },
  { title: 'Important warnings', warning: 'Starting discovery sends real network probes. Use authorized targets only and do not run broad or repeated scans on production networks without approval. The page has no visible Stop/Cancel button. Automatic topology ICMP polling is separate from manual discovery and runs while this page is visible. Delete, Delete Selected, and Delete All operate on saved NMS inventory, not temporary scan results; device deletion can also remove related device data. Never use DELETE ALL to clear scan results.' },
  { title: 'Troubleshooting', body: 'No results: verify target range, network route, power state, firewall, and ICMP reachability. Invalid target: use a supported IPv4 address, range, list, or /24–/32 CIDR and stay within 255 addresses. No SNMP details: check SNMP enablement, allowed NMS host, credentials, and UDP 161. Slow scan: reduce target size; enrichment and timeouts may add delay. Missing button or access denied: ask an administrator to review role permissions.' },
  { title: 'Frequently asked questions', faqs: [['Does scanning save devices?', 'No. Use + Add or Store all.'], ['Can I export results or see scan history?', 'Not on this page.'], ['Can I stop a scan here?', 'No visible Stop button is implemented.'], ['Does adding a device immediately start live monitoring?', 'Not explicitly from this page; verify the monitoring engine separately.'], ['Does topology show unsaved scan results?', 'No. It shows saved devices.']] },
  { title: 'Known limitations', body: 'There is no scan-history page or scan-result export. No visible scan cancellation control is implemented. Adding a device has no explicit monitoring-start action from this page. Live behavior of site filtering, backend discovery authorization, deletion cascades, production network impact, and automatic monitoring startup remains to be verified. The SNMP modal and post-scan results were not pictured in the supplied documentation.' },
]

const allDevicesSections: Section[] = [
  { title: 'Introduction', body: 'All Devices is the central list of devices already known to AgniGate NMS. It shows saved identity, connectivity, and monitoring information. Use it to view, filter, and open device details; this page does not scan the network or change device inventory.' },
  { title: 'Screen overview', body: 'The page contains four summary cards, a local search and filter panel, the device inventory table, and a VIEW DETAILS action for each row. The page is a read-only inventory view.' },
  { title: 'Summary cards', body: 'TOTAL DEVICES shows the number of loaded devices and clears status and protocol filters when selected. ONLINE filters to saved online/up status. OFFLINE filters to saved offline/down status. SNMP CONFIGURED filters to devices with an SNMP credential or version recorded.' },
  { title: 'Search and filters', body: 'Search name, IP, MAC, vendor or model is case-insensitive and filters the loaded rows locally. All statuses offers Online and Offline. All protocols offers ICMP, SNMP, and ICMP + SNMP. Search and filters can be combined. They do not change saved devices or send new scan requests.' },
  { title: 'Device inventory table', body: 'Device Name shows the saved hostname or name. IP Address and MAC Address show recorded network addresses. Vendor / Model shows identifying information when available. Site shows the site identifier and may show a dash. Status shows the latest saved online, offline, or other status. ICMP is the monitoring configuration indicator. SNMP shows whether SNMP is configured. Last Seen shows the last recorded observation time in Asia/Kolkata. VIEW DETAILS opens the selected device details page.' },
  { title: 'View Details and device information', steps: ['Open All Devices from the sidebar.', 'Search by device name or IP, or use a summary card/filter.', 'Find the correct row and select VIEW DETAILS.', 'Review Device Overview, Inventory / System Information, and Connectivity / Protocols.', 'Use detail-page navigation only when you have the required access.'], body: 'Device Overview can show name, IP, MAC, device type, vendor/model, site, status, and Last Seen. Inventory / System Information can show device ID, serial number, firmware, and recorded uptime/downtime when available. Connectivity / Protocols covers ICMP, SNMP, and monitoring indicators. VIEW MONITORING, SNMP DEVICE, and REMOTE ACCESS are destination-module navigation actions whose availability and permissions depend on the detail page. ALL DEVICES returns to the inventory list.' },
  { title: 'Monitoring and protocol indicators', body: 'Online or Offline is the latest stored backend status; this page does not run a live probe or automatically refresh. Review Last Seen and device monitoring details before drawing conclusions. SNMP CONFIGURED means configuration is recorded; it does not guarantee successful SNMP communication. ICMP and SNMP table values are configuration indicators returned by the API, not fresh tests from this page.' },
  { title: 'Permissions and access', body: 'The All Devices sidebar and page require device_monitoring:read. The device-list API separately requires devices:read. Users who can open the page but lack API permission may see an authorization error. The backend limits the list to sites accessible to site-restricted accounts.' },
  { title: 'Step-by-step daily workflow', steps: ['Review Total, Online, and Offline counts.', 'Search for important devices by hostname or IP.', 'Filter Offline to investigate affected devices.', 'Check Last Seen to understand how recent the status is.', 'Open VIEW DETAILS to inspect the device.', 'Escalate unexpected status or missing data to the responsible administrator.'] },
  { title: 'Important warnings', warning: 'All Devices has no Add, Edit, Delete, or Delete All controls. Other NMS workflows may change or permanently delete device records and associated monitoring history. Never treat inventory deletion as a way to clear a filter or refresh a list. A missing device may be outside your site access, not necessarily deleted. Search and filters affect only the currently loaded list. Do not assume Last Seen or status is a real-time test result.' },
  { title: 'Troubleshooting', body: 'No devices: confirm account permissions and site access. Device not found: clear search and filters; the page may load only the first 100 records. Status seems outdated: check Last Seen and open Device Monitoring. SNMP not configured: review the device’s SNMP setup in the appropriate module. Page/API error: retry or ask an administrator to check API access and service health.' },
  { title: 'Frequently asked questions', faqs: [['Does All Devices scan the network?', 'No. It reads the saved device inventory.'], ['Does filtering change device data?', 'No. Filters only change which loaded rows are shown.'], ['Can I delete devices from this page?', 'No. There is no delete action on the All Devices page.'], ['Is device status live?', 'Not from this page. It displays the latest saved backend status.'], ['Why are some devices missing?', 'Site permissions, filters, or the first-100-device loading limit may be responsible.'], ['Does VIEW DETAILS edit a device?', 'No. It opens the details page; separate actions there may have different permissions.']] },
  { title: 'Known limitations', body: 'The page loads the first 100 devices by default, has no visible pagination, export, or refresh button, and does not perform live polling. The Site column may display a numeric site ID instead of a readable site name. Device Details behavior may vary by device type and requires separate live verification.' },
]

const windowsSections: Section[] = [
  { title: 'Introduction', body: 'Windows Devices registers authorized Windows PCs and Servers, validates WinRM connectivity, and displays saved Windows monitoring data. Windows-side preparation and NMS-side onboarding are separate activities.' },
  { title: 'Prerequisites', steps: ['Obtain authorization to monitor the Windows PC or Server and confirm the correct NMS site.', 'Identify a stable hostname or DNS name, or a reachable IP address.', 'Prepare a least-privilege Windows or Active Directory monitoring account.', 'Configure WinRM HTTPS, the server certificate, firewall access and required Windows permissions on the target.', 'Confirm the NMS user has the required device and site permissions.'], warning: 'NMS does not create Windows user accounts, enable WinRM, create certificates, or open the Windows firewall. Those steps must be completed by an authorized Windows administrator.' },
  { title: 'How Windows data reaches NMS', body: 'The collection path is Windows host → WinRM HTTPS on TCP 5986 → authenticated PowerShell/WMI-CIM queries → NMS Windows collector → saved monitoring snapshots. FETCH actions and connection tests use the configured hostname/IP, Windows credentials and certificate trust. A saved snapshot can be older than the current Windows state.' },
  { title: 'Windows-side monitoring account', body: 'Create or provision the monitoring account on Windows or in Active Directory before using NMS. Use an organization-approved least-privilege account. Local/workgroup accounts use the target computer name as the computer context; domain accounts use the approved Active Directory domain. Do not paste passwords into documentation or shell history, and do not grant local Administrator membership by default.' },
  { title: 'Identity and connection fields', body: 'Hostname is the Windows computer name. IP Address is the address reachable from NMS. Connection Host is the WinRM target used for the connection and may be a DNS name or IP. For TLS, prefer a hostname matching the certificate SAN. The Username, Password and Domain / Computer Name fields describe the Windows account used by WinRM; NMS stores the password encrypted and does not return it in credential-read responses.' },
  { title: 'WinRM HTTPS and TLS trust', body: 'The current Windows flow uses HTTPS with NTLM on TCP 5986. The Windows host needs an HTTPS listener with a valid server-authentication certificate whose SAN matches the connection host. The issuing CA must be trusted by the NMS configuration. HTTP on TCP 5985 is not the connection mode used by this flow. Do not disable certificate verification to force a connection.' },
  { title: 'Add Windows Device — three-step wizard', steps: ['Step 1 — Device: select an existing inventory record or choose Add a new Windows device manually; enter connection host, hostname, IP and authorized site, then select CONTINUE.', 'Step 2 — Windows Credentials: enter the monitoring username, domain/computer name and password, then select CONTINUE.', 'Step 3 — Test: review the identity, site and account context, then select SAVE & TEST CONNECTION.'], warning: 'Save & Test is not a preview. It can create inventory and credentials and initiate traffic to the Windows host. If validation fails, the records may already have been saved; avoid repeatedly creating duplicate devices.' },
  { title: 'Save & Test Connection', body: 'The save operation creates or uses the inventory device, saves the Windows credential, and attempts WinRM connection validation. TCP reachability alone does not prove TLS trust, authentication, PowerShell authorization or CIM access. Open DETAILS to review saved monitoring data, trust status and available diagnostics.' },
  { title: 'Inventory and status', body: 'The list shows Windows devices, summary counts, search by hostname/IP/ID, status filtering, DETAILS and DELETE. Status is saved monitoring evidence, not proof of a live connection at this moment. Last Collected identifies the age of saved data. DELETE is destructive; the exact monitoring-history deletion cascade was not verified.' },
  { title: 'Overview and system information', body: 'Overview can show hostname, device ID, status, CPU, RAM, disk capacity, network adapters, OS version/build and hardware summary. FETCH SYSTEM INFO requests current supported system information and saves the result. Review Last Collected before treating displayed data as current.' },
  { title: 'CPU and Memory', body: 'FETCH CPU collects CPU utilization, cores, threads, processes, speed and per-core usage. FETCH MEMORY collects total, used and available RAM, committed memory and cache/pool categories. The supplied UI states that historical CPU and Memory samples are not stored; do not promise continuous historical charts.' },
  { title: 'Disk, Network and Hardware', body: 'FETCH DISK collects disk capacity and performance information. FETCH NETWORK collects adapter identity, link speed, receive/transmit rates and connection status; Search, status filtering and VIEW expand adapter details. FETCH HARDWARE collects manufacturer, model, processor, memory, motherboard and BIOS information. Native sensor discovery is supported where Windows hardware/provider support is available.' },
  { title: 'Storage and disk health', body: 'Storage is separate from the Disk metrics tab. It displays physical disk inventory and health/provider information. A Windows WSMan or storage-provider fault can affect health data while inventory remains available; investigate the provider and WinRM/CIM error separately.' },
  { title: 'Windows Event Logs', body: 'FETCH SYSTEM EVENTS retrieves and saves System-channel events. Event ID, severity and date filters can be applied with APPLY or cleared with CLEAR. PREVIOUS and NEXT paginate the returned records. The current endpoint exposes the System channel, not all Windows event-log channels.' },
  { title: 'USB inventory', body: 'The USB tab displays controller, hub and connected-device inventory with presence/health indicators. REFRESH USB requests current information. The panel is read-only; it is not a USB blocking or remote device-control interface.' },
  { title: 'Threshold Settings', body: 'Authorized users can view and update CPU, memory and disk thresholds. Threshold changes modify monitoring configuration and may influence alert generation. Confirm values against workload and organizational policy before saving.' },
  { title: 'TCP and TLS diagnostics', body: 'TEST TCP checks whether WinRM HTTPS port 5986 is reachable. VERIFY TLS checks certificate chain, validity and hostname matching. The normal connection test validates WinRM access. CA upload, assign/replace, remove and revoke actions change trust configuration and require separate CA permissions. A WinRM diagnostic backend exists, but no WinRM diagnostic button is rendered in the current page.' },
  { title: 'Permissions and security', body: 'Page access requires device_monitoring:read. Device listing and saved data use devices:read. Creating inventory uses devices:create. Credential updates, FETCH actions, connection tests and threshold changes use devices:update. Deletion uses devices:delete. CA trust uses windows_ca:read, windows_ca:manage and windows_ca:assign. Backend site-access checks also apply. Passwords are encrypted at rest and omitted from read responses.' },
  { title: 'Troubleshooting', body: 'Device unreachable: verify DNS, routing, Windows availability, TCP 5986 and firewall scope. TCP passes but TLS fails: check certificate expiry, chain, CA assignment and SAN matching. TLS passes but authentication fails: verify the Windows account, username, domain/computer name, password and NTLM policy. Authentication passes but CIM fails: review remote PowerShell, WinRM and WMI/CIM permissions. Storage WSMan fault: inspect the Windows provider and WinRM logs. Metrics are blank or old: review Last Collected and use the relevant FETCH only when authorized.' },
  { title: 'Safe operating checklist', steps: ['Confirm authorization, site and Windows-side prerequisites.', 'Use a dedicated least-privilege monitoring account.', 'Verify WinRM HTTPS 5986, certificate identity and firewall access.', 'Use a certificate-matching connection host.', 'Review all fields before SAVE & TEST CONNECTION.', 'Check TCP, TLS, authentication and CIM in that order.', 'Fetch only the modules needed and review Last Collected.', 'Assess impact before CA revocation or device deletion.'] },
  { title: 'Frequently asked questions', faqs: [['Does NMS create the Windows account?', 'No. Create or provision it on Windows or in Active Directory first.'], ['Which port is used?', 'WinRM HTTPS on TCP 5986 with NTLM authentication.'], ['Can I use an IP address?', 'Yes, but TLS validation must match the certificate identity; a matching stable DNS name is usually easier.'], ['Does Save & Test enable WinRM?', 'No. WinRM, firewall, account permissions and certificates must already be prepared on Windows.'], ['Does TCP success mean metrics will work?', 'No. TLS, authentication, PowerShell and CIM authorization must also succeed.'], ['Is historical CPU or Memory data available?', 'The supplied UI states those historical samples are not stored.'], ['Can I manage Windows services here?', 'No separate Windows service/process-management controls are exposed in the audited page.']] },
  { title: 'Known limitations', body: 'The page has no list pagination, bulk operations or export. Historical CPU and Memory samples are not stored. The WinRM diagnostic backend exists but its button is not rendered. Live connectivity, restricted-user site behavior, exact deletion cascades and production error behavior require controlled verification.' },
]

const snmpSections: Section[] = [
  { title: 'Introduction and monitoring architecture', body: 'SNMP Devices lets NMS query authorized network devices through their SNMP agents. NMS sends requests, reads supported OIDs, interprets responses and stores inventory and monitoring data. CPU, memory, interfaces, traffic, storage, routing, ARP and topology data depend on the device agent and supported OIDs. Stored readings represent the last successful poll, not necessarily the current device state. SNMP traps are separate and are not configured by this page.' },
  { title: 'Device-side prerequisites', steps: ['Obtain authorization, the correct device address, site assignment and an approved read-only SNMP account or community.', 'Enable the SNMP agent on the target device using its vendor-supported GUI or CLI.', 'Allow SNMP queries from the NMS server in device ACLs and firewalls.', 'Permit UDP destination port 161 and verify routing and response traffic.', 'Choose a strong unique read-only v2c community, or a matching SNMPv3 account.', 'Confirm the device clock and expected MIB/OID support.'], warning: 'Vendor commands vary. Follow the device manufacturer documentation and do not paste commands intended for another platform.' },
  { title: 'SNMPv2c and SNMPv3 security', body: 'SNMPv1/v2c uses the same community string on the device and NMS, the selected version and UDP port 161. Community strings are credentials, but v1/v2c does not provide SNMPv3-style privacy. SNMPv3 uses a username and security level: noAuthNoPriv, authNoPriv or authPriv. The audited form offers MD5 or SHA authentication and DES or AES privacy. Prefer authPriv and mutually supported algorithms. Never include real community strings, production usernames or passwords in screenshots.' },
  { title: 'Add SNMP Device workflow', steps: ['Open SNMP Devices and select ADD DEVICE.', 'Enter IP Address and Device Name or Hostname; add optional MAC and description.', 'Choose SNMPv1, SNMPv2c or SNMPv3 and confirm the port, normally 161.', 'For v1/v2c enter the approved community string. For v3 enter username, security level and applicable authentication/privacy settings.', 'Assign the correct site and add vendor, model or device-type overrides only when known.', 'Choose whether to run full SNMP discovery after adding. Leave it off initially when cautious.', 'Review all fields and select ADD DEVICE.', 'Return to the inventory, refresh, open the row and verify status, capabilities, Last Seen and Last Poll.', 'Enable only the monitoring modules required for the device.'], warning: 'Adding a device saves inventory and credentials. Optional automatic discovery sends real SNMP requests. The Add Device test helper does not perform a pre-creation live test, and the visible list-page Test SNMP action is currently a placeholder.' },
  { title: 'Discover and Store', body: 'The discovery panel supports a single IP, an IP range or prefix mode where available. Enter an authorized target, choose v1/v2c/v3, provide matching credentials and security settings, set the available timeout, then start the discovery action shown by the UI. Review progress, identity and capabilities before storing selected or all results. Start with one IP to avoid excessive traffic and confirm the correct site and duplicates before saving.' },
  { title: 'Device inventory and management', body: 'The inventory includes Name, IP Address, Hostname, MAC Address, SNMP version, SNMP Status, device Status, Monitoring status, Modules, Last Seen, Last Poll and Actions. Search by IP, hostname or MAC. Use sortable headers, REFRESH, page sizes 25/50/75/100 and PREV/NEXT. Single-click selects and prefetches; double-click opens details. Configure Monitoring opens module controls. Edit Device saves inventory changes. Delete Device and DELETE SELECTED require confirmation and can remove monitoring data and jobs.' },
  { title: 'Device details, capabilities and status', body: 'Device Details provides Overview, Monitoring, Metrics and History tabs, REFRESH, VIEW MONITORING and CONFIGURE MONITORING. It shows identity, vendor/model, status, SNMP version, Last Seen, capability tiles and available data sections. Supported modules depend on the target agent and OIDs. A supported tile may still have no history until successful polling; an unavailable tile is not automatically an NMS fault.' },
  { title: 'Monitoring modules', body: 'Available modules may include CPU, Memory, Storage, Interfaces, Routing, ARP, SNMP-derived Topology, System, Environment, VLAN, LLDP, CDP, MAC Table, Firewall, Wireless, Inventory, Health, OID Explorer and Polling. Module availability varies by device capabilities and returned OIDs. Do not assume every listed module is available for every device.' },
  { title: 'Polling intervals and monitoring controls', steps: ['Open device details and choose CONFIGURE MONITORING or a module page.', 'Select only modules reported as supported.', 'Set the available polling interval according to policy.', 'Start required modules individually and confirm RUNNING or healthy status.', 'Review Last Poll and latest values rather than relying only on the running label.', 'Stop a module only when authorized; stopping collection may affect alerts and history continuity.'], warning: 'Polling, discovery and starting modules send network traffic. A RUNNING status does not prove the last poll succeeded, and an unreachable device may still show older stored data.' },
  { title: 'Permissions and security', body: 'devices:read is required for inventory, details and metrics. devices:create is required to add devices. devices:update is required to edit, discover, poll and start or stop modules. devices:delete is required for deletion. Backend site-scope checks restrict devices to authorized sites. Community strings and SNMPv3 authentication/privacy secrets are encrypted by the inspected add flow and must never be shared in documentation.' },
  { title: 'Deletion warning', warning: '⚠️ WARNING: Deleting an SNMP device from NMS may permanently remove its stored monitoring history. Re-adding the same device will not automatically restore previously deleted historical records. Confirm backups and authorization before deletion.' },
  { title: 'Troubleshooting', body: 'Device absent: check search, pagination, site scope and permissions. Timeout: verify IP, routing, ACL/firewall, UDP 161, the SNMP agent and timeout. Authentication error: verify version, community or v3 username, security level, authentication and privacy protocols. Missing CPU, memory or storage: verify capabilities, supported OIDs and successful polling. Stale metrics: compare Last Seen, Last Poll, monitoring status and interval. Module unavailable: the device may not support the required data. Discovery issue: reduce to one authorized IP and verify device-side SNMP access first.' },
  { title: 'Frequently asked questions', faqs: [['Does adding a device always scan it?', 'No. Saving inventory and credentials is separate. Optional automatic discovery contacts the target when enabled.'], ['Does SNMPv3 always encrypt traffic?', 'No. Only authPriv provides privacy/encryption when correctly configured.'], ['Does the visible Test SNMP action prove connectivity?', 'No. The current audited list action is a placeholder even though a backend test endpoint exists.'], ['Can a deleted device recover its old data?', 'Do not rely on recovery. Deleted monitoring records are not automatically restored by re-adding the device.'], ['Are all monitoring modules available?', 'No. Availability depends on the device, its agent and supported OIDs.']] },
  { title: 'Known limitations', body: 'MIB upload and management were not found. Dedicated SNMP threshold editing was not found in this module. The visible Test SNMP action is not fully wired to its backend endpoint. Exact vendor interoperability, deletion cascades, live reachability and runtime behavior require controlled verification.' },
]

const deviceMonitoringSections: Section[] = [
  { title: 'Introduction and page overview', body: 'Device Monitoring shows the saved device inventory alongside the current ICMP monitoring state. It provides summary counters, per-device controls, and a detailed monitoring view for availability and network reachability. The page reports information collected by NMS; opening it does not itself start a scan.' },
  { title: 'Summary counters', body: 'TOTAL DEVICES is the number of devices loaded from the accessible inventory. MONITORED is the number currently reported by the real-time monitoring engine. ONLINE and OFFLINE are the engine’s confirmed UP and DOWN counts. These counters describe the current in-memory monitoring snapshot and may differ from older stored device status until polling confirms a state.' },
  { title: 'START ALL and STOP ALL', steps: ['Use START ALL to request active monitoring for the devices currently loaded in the list.', 'Wait for the monitoring status and device rows to update before interpreting the counters.', 'Use STOP ALL to stop active monitoring for all devices managed by the monitoring engine.', 'Confirm the resulting status before leaving the page.'], warning: 'START ALL and STOP ALL change active monitoring state. They do not delete stored metrics or status history. They do send ICMP traffic when monitoring runs.' },
  { title: 'Individual START and STOP', body: 'Each device row can start or stop monitoring independently. START sends the device information to the monitoring engine; STOP identifies the device by IP and stops its active monitor. A row without a live sample is shown as NOT MONITORED. These controls do not delete stored history. Permission-gated controls require monitoring:execute in the frontend; backend discovery-monitoring authorization requires separate verification.' },
  { title: 'VIEW MONITORING', body: 'Select VIEW MONITORING for a device to open its detailed route at /device-monitoring/{deviceId}. The detail view combines the latest live sample with stored metrics, status transitions, availability calculations, live ping history, and the exact UP/DOWN timeline.' },
  { title: 'ICMP polling and device status', body: 'The real-time monitor polls with ICMP approximately every 15 seconds and uses a 1-second ping timeout. A state change is confirmed after two consecutive matching results: two successes for UP or two failures for DOWN. RTT is shown for reachable responses; failed responses contribute to packet loss and may show no RTT. Live status is distinct from the last stored device status.' },
  { title: 'Availability, uptime and downtime', body: 'The detail view calculates availability for the requested history window from stored status transitions and metric records. It shows availability percentage, uptime, downtime, status-change totals, ping counts, and the current status. The exact timeline walks each recorded state until the next transition or the present time. The fallback lifetime values are device fields and should not be confused with the calculated window.' },
  { title: 'Latency & Packet Loss', body: 'The chart uses up to 200 fetched metric records and groups them into five-minute buckets. Each bucket displays average latency and average packet loss. The detail page refreshes metric and status-history data every 15 seconds while visible; the chart therefore reflects stored samples available at each refresh, not an unbounded live stream.' },
  { title: 'Live Ping History', body: 'Live Ping History contains the latest 20 entries held in the real-time monitor’s in-memory history for the device. It can include UP/DOWN results, RTT, timeouts, and timestamps. Because this list is in memory, it is not the authoritative long-term record and may reset when the monitor process restarts.' },
  { title: 'Status Change History', body: 'Status Change History displays verified online/offline transitions from the stored device status history for the latest 24 hours, with a maximum of 100 transitions. The list is paginated in the UI. It is historical database data, not the same as the current live stream.' },
  { title: 'Exact UP/DOWN timeline', body: 'Open VIEW EXACT UP/DOWN TIMELINE from the availability card to review each recorded period, its start and end, duration, state, and evidence. The timeline is derived from stored status transitions over the selected history window. An open current period is measured through the present time, so it can change as time passes.' },
  { title: 'Monitoring data collection and storage', body: 'The monitor performs concurrent ICMP checks on its approximately 15-second loop, confirms transitions after two consecutive results, keeps the latest 20 live samples in memory, and persists metric samples and confirmed status changes. Stored metrics include latency/RTT and packet-loss values derived from the result. Historical APIs expose a default 24-hour window; the detail chart requests up to 200 metric records.' },
  { title: 'Permissions and security limitations', body: 'The sidebar and both monitoring pages are protected by device_monitoring:read. START/STOP controls are displayed through the frontend monitoring:execute guard. Normal device details, metrics, and status-history APIs use device-read permissions and site access checks. The inspected discovery monitoring start, stop, status, stream, and device-history endpoints do not visibly declare equivalent RBAC/site-scope dependencies; backend enforcement for those endpoints requires separate remediation and verification. Do not treat a visible control as proof that every backend path is fully authorized.' },
  { title: 'Troubleshooting', body: 'No live result: confirm the device is in accessible inventory and monitoring is running. Status remains DOWN: verify IP reachability and investigate firewall or routing before assuming a permanent outage. RTT is blank: the latest ICMP attempt did not provide a usable response. Values look old: check Last Check, Last Seen, the monitoring status, and whether the monitor loop is running. History is empty: the device may not have been monitored long enough or may have no records in the selected window. Permission errors: ask an administrator to verify device_monitoring:read, monitoring:execute, device permissions, and site visibility.' },
  { title: 'Frequently asked questions', faqs: [['Does STOP MONITORING delete history?', 'No. STOP changes active monitoring state; it does not delete stored metrics or status history.'], ['Does START ALL scan the network?', 'It starts ICMP monitoring for the loaded devices, which produces network traffic at the monitoring interval.'], ['Why do Online and Offline differ from a device status field?', 'The counters use the current monitoring engine snapshot, while a device field may be older stored information.'], ['How long is Live Ping History retained?', 'The monitor keeps the latest 20 entries in memory.'], ['How much Status Change History is shown?', 'The detail view requests the latest 24 hours and displays at most 100 transitions.'], ['Does deleting a device equal stopping monitoring?', 'No. Deleting is a separate inventory action and can remove monitoring history and associated records.']] },
  { title: 'Important warning — device deletion and history loss', warning: '⚠️ WARNING — DEVICE DELETION AND HISTORY LOSS\n\nDeleting a device from NMS can permanently delete its monitoring metrics, status history and associated records.\n\nRe-adding the same device does NOT automatically restore its previously deleted monitoring history.\n\nSTOP MONITORING and DELETE DEVICE are different actions.' },
  { title: 'PDF actions', body: 'Use View PDF to open the approved Device Monitoring User Guide in a new tab. Use Download PDF to save the same guide as AgniGate_NMS_Device_Monitoring_User_Guide.pdf.' },
]

const packetAnalysisSections: Section[] = [
  { title: 'Page overview and actual data sources', body: 'Packet Analysis combines three read-only sources: the Overview API for stored device, interface and alert information; the Device Metrics API for stored metric records; and the monitoring-status API for current in-memory ping counters. It does not read PCAP files, capture packets, inspect payloads, or run a DPI engine.' },
  { title: 'Important warning', warning: 'Packet Analysis currently does NOT perform actual\nPCAP capture or Deep Packet Inspection (DPI).\nProtocol Distribution is estimated, and some\ndisplayed packet-like data is synthetic.\nDo not treat these visualizations as forensic\nevidence of captured network traffic.' },
  { title: 'Summary cards', body: 'Total Traffic adds the displayed inbound and outbound interface values. Traffic In sums interface receive values. Traffic Out sums interface transmit values. Packet Errors sums the latest interface error values. Monitored Pings sums total_pings reported by the real-time monitoring engine. These values are NMS telemetry aggregates, not captured-packet totals.' },
  { title: 'Protocol Distribution', body: 'The protocol chart is an estimate generated in the browser. TCP, UDP, HTTP/S, DNS and SSH use fixed ratios of interface inbound/outbound totals. ICMP is estimated from monitored ping counts. Other is the remaining calculated amount. No protocol headers, packet payloads, PCAP records, or DPI results are used.' },
  { title: 'Traffic Flow Analysis', body: 'The chart uses up to the latest 30 stored DeviceMetric records. Its displayed bytes and packet values are derived frontend visualization fields, not packet-capture measurements. When no metrics exist, the page generates fallback points for presentation. Treat this chart as an operational trend visualization only.' },
  { title: 'Suspicious Packet Detection', body: 'This section maps up to 10 recent open or acknowledged device alerts into packet-like rows. Protocol, source, destination, size and packet ID can be inferred or generated from alert text and device data. Clicking a row opens a detail modal containing the alert context. No packet payload or forensic evidence is available.' },
  { title: 'Interface Traffic Breakdown', body: 'The table shows the selected device, IP, interface, status, speed, inbound traffic, outbound traffic, total and errors from the latest stored interface records. The backend selects one latest row per device/interface and classifies freshness, but the page does not display the freshness label. Values are supplied as interface telemetry fields; confirm units with an administrator before treating them as byte counters.' },
  { title: 'Refresh and update behavior', steps: ['Open Packet Analysis from the sidebar.', 'The page loads stored overview data, device metrics and monitoring status.', 'The page refreshes automatically every 30 seconds while mounted.', 'Select REFRESH to request the same data sources immediately.', 'Review timestamps and related monitoring pages before acting on stale-looking values.'], warning: 'REFRESH does not start PCAP capture, DPI, network discovery, or a new packet inspection job.' },
  { title: 'Step-by-step usage', steps: ['Check the five summary cards for a high-level telemetry snapshot.', 'Review Protocol Distribution as an estimate, not measured protocol traffic.', 'Review Traffic Flow Analysis for stored-metric trends.', 'Open a suspicious alert row to inspect its mapped alert details.', 'Review Interface Traffic Breakdown for device/interface status and recorded values.', 'Use Device Monitoring or interface-specific pages for authoritative operational investigation.'] },
  { title: 'Permissions and site visibility', body: 'The route requires packet_analysis:read. The Overview data source requires dashboard:read; stored device metrics require device_metrics:read or devices:read. Backend Overview, device metrics and alerts apply accessible-site filtering where their normal APIs are used. Monitoring status is obtained from a discovery monitoring endpoint whose equivalent RBAC and site-scope enforcement requires separate verification.' },
  { title: 'Troubleshooting', body: 'No data: verify device inventory, site visibility and the required permissions. Interface rows missing: check whether interface monitoring has collected records and whether the data is stale or missing. Metrics chart empty: confirm Device Metrics records exist. Unexpected protocol percentages: remember that they are hard-coded estimates. Suspicious rows look like packets: they are alert-derived display records, not captures. Values appear old: inspect Last Seen, polling status and timestamps in the relevant monitoring pages.' },
  { title: 'Frequently asked questions', faqs: [['Does this page capture packets?', 'No. It reads stored NMS telemetry, alerts and monitoring counters.'], ['Is Deep Packet Inspection implemented?', 'No verified DPI implementation is used by this page.'], ['Are protocol percentages measured?', 'No. They are frontend estimates based on interface totals and ping counts.'], ['Are Traffic In and Traffic Out PCAP byte totals?', 'No. They are derived from interface telemetry fields and their displayed byte units should be treated cautiously.'], ['Can I filter or export packet data?', 'No filters, pagination, export, PCAP upload, or packet download controls are implemented.'], ['Does REFRESH start monitoring?', 'No. It refreshes the page data sources; it does not start packet capture or discovery.']] },
  { title: 'Known limitations', body: 'There is no PCAP capture, packet parser, DPI engine, protocol-header inspection, payload inspection, packet export, date filter, device filter, interface filter, protocol filter, pagination, or capture control. Protocol values, packet IDs, packet sizes and some addresses are synthetic or inferred. Traffic values may be misleadingly formatted as bytes even though the backend fields are rate-like interface values. No page-level retention or deletion controls are implemented.' },
  { title: 'PDF actions', body: 'Use View PDF to open the approved Packet Analysis User Guide in a new tab. Use Download PDF to save it as AgniGate_NMS_Packet_Analysis_User_Guide.pdf.' },
]

const reportSections: Section[] = [
  { title: 'Report Center overview', body: 'Report Center provides two views: Reports and Scheduled Reports. Reports summarize stored SNMP, ICMP, device-status, alert, interface and performance data. Scheduled Reports define recurring CSV, XLSX or PDF report jobs and provide access to completed generated files.' },
  { title: 'Reports: filters and date ranges', body: 'Use Period (Today, Yesterday, Weekly, Monthly, Yearly or Custom), Protocol (SNMP + ICMP, SNMP or ICMP), Site, Device type, Status, Alert severity and Device filters. Custom ranges require Start date and End date. Apply filters to request a new report. Weekly, monthly and yearly interactive ranges are rolling lookback windows; scheduled weekly/monthly reports use completed calendar windows.' },
  { title: 'Summary cards and trends', body: 'The Reports view shows Total, Up, Down and Unreachable devices; Total and Critical alerts; Total outages; and Average availability. Additional rows show alert states, Alert MTTR, SLA configured/met/breached/unknown counts, and inventory assets. Historical charts cover availability, alerts, performance and bandwidth using stored status, alert, metric and interface records. Empty or unknown data is not automatically treated as healthy.' },
  { title: 'Device report and View Details', body: 'The device table includes device identity, site, protocol, availability, downtime, outages, status, SNMP health, performance, interfaces, alerts and SLA. Search filters the loaded rows by hostname, IP, site or device type. View Details opens the selected record with overview, asset information, performance, interface details and alert details. Interface and alert detail lists may be limited to 100 records.' },
  { title: 'Export actions', steps: ['Apply the required report filters.', 'Select Export and choose PDF, CSV or Excel.', 'Wait for the export operation to finish before navigating away.', 'Treat the resulting file as sensitive operational data.'], body: 'CSV and Excel are generated in the browser from a fresh report response. The frontend PDF uses the report PDF renderer. A separate backend export endpoint supports CSV; scheduled reports use backend CSV/XLSX/PDF generators.' },
  { title: 'Scheduled Reports and New Schedule', body: 'Open Scheduled Reports and select New schedule. Enter a name, choose Daily, Weekly or Monthly frequency, set the run time, choose CSV, XLSX or PDF, choose whether the schedule is enabled, and configure site, device, device type, status, protocol and alert-severity filters. Save creates the schedule only after permission and scope validation.' },
  { title: 'Schedule frequency and execution', body: 'Daily schedules cover the previous calendar day. Weekly schedules cover the previous seven completed days and are registered for Monday execution. Monthly schedules cover the previous calendar month and are registered for day one. The scheduler uses the schedule timezone, prevents overlapping instances, coalesces missed runs, and allows a one-hour misfire grace period. Actual production execution requires live operational verification.' },
  { title: 'Schedule management', body: 'Use Edit to change the name, frequency, run time, format, enabled state or filters. Use Enable or Disable to activate or pause a schedule. Use Delete and confirm to remove the schedule. Deleting a schedule removes its scheduler job while generated report history is intended to remain preserved.' },
  { title: 'Generated Reports and downloads', body: 'The Generated Reports table shows report name, covered period, generation time, format, file size and status. Only SUCCESS entries expose Download. The backend validates the generated file path before returning CSV, XLSX or PDF content. Failed jobs retain a failure status and error message rather than exposing a file.' },
  { title: 'Permissions and site visibility', body: 'Viewing reports, options, schedules and generated reports requires reports:read. Creating schedules requires reports:schedules:create; editing or enabling/disabling requires reports:schedules:update; deleting requires reports:schedules:delete. Schedule ownership and scope are revalidated for non-super-admin users. Important limitation: the main report endpoint does not visibly apply accessible-site filtering when no explicit site or device scope is supplied, so full site isolation is not verified.' },
  { title: 'Availability, downtime, SLA and MTTR', body: 'Availability and downtime are derived from stored DeviceStatusHistory intervals. Unknown periods are excluded from the known availability denominator. Outage count and duration depend on recorded transitions. SLA status compares calculated availability with the configured target. Alert MTTR is the average duration of resolved alerts; do not automatically interpret it as physical outage MTTR.' },
  { title: 'Troubleshooting and warnings', body: 'No devices: check permissions, site scope and filters. No availability: verify status history exists for the selected period. Empty trends: confirm stored metrics, interface statistics or alerts exist. Schedule not visible: verify ownership, scope and reports:read. Schedule failed: review its FAILED status and error message. Download unavailable: only SUCCESS reports have files. Exports and generated reports can contain IPs, MACs, sites, inventory, alerts and performance data.' },
  { title: 'Known limitations and FAQs', faqs: [['Does Report Center perform live polling?', 'No. Reports read stored monitoring, status, alert and interface data.'], ['Does creating a schedule run it immediately?', 'No. It creates or updates a recurring scheduler definition.'], ['Are scheduled-report emails supported?', 'User-created scheduled reports generate files. Separate daily email functionality exists, but email delivery for these schedules is not verified.'], ['Are all export formats handled by the backend?', 'The visible frontend supports PDF, CSV and Excel. The backend management export endpoint supports CSV; scheduled generation supports all three formats.'], ['How much detail is shown?', 'Interface and alert details can be capped at 100 records.'], ['Does deleting a schedule delete generated reports?', 'The code intends to preserve generated report history, although access to detached history can depend on authorization.']] },
  { title: 'Important warning — report scope and sensitive data', warning: 'Review site and device scope before generating or scheduling a report. Report files may contain sensitive operational data including IP addresses, MAC addresses, inventory, alerts, availability and performance information. Full site isolation for an unrestricted main report request is not verified and requires remediation.' },
  { title: 'PDF actions', body: 'Use View PDF to open the approved Report Center User Guide in a new tab. Use Download PDF to save it as AgniGate_NMS_Report_Center_User_Guide.pdf.' },
]

const linuxSections: Section[] = [
  { title: 'Module overview and prerequisites', body: 'Linux Server Monitoring maintains a separate Linux server inventory. SSH is used for initial detection and security-log collection; recurring metrics use SNMPv3. Prepare an authorized Linux host, SSH access, an SNMP agent, an SNMPv3 authPriv user, and network access from NMS before onboarding.' },
  { title: 'Linux-side requirements', steps: ['Enable SSH and create an authorized monitoring account on the Linux server.', 'Install and configure a compatible SNMP agent such as net-snmp according to the distribution documentation.', 'Create an SNMPv3 authPriv user with matching authentication and privacy settings.', 'Permit the NMS backend to reach the SSH port, normally TCP 22, and SNMP UDP 161.', 'Ensure the SNMP view exposes the required IF-MIB, HOST-RESOURCES-MIB, UCD-SNMP-MIB and DISKIO data.'], warning: 'Distribution support is not restricted by an explicit allowlist. Compatibility depends on standard Linux interfaces, SSH, SNMPv3 and accessible MIB/OID data.' },
  { title: 'Detect / Add Server workflow', steps: ['Select Detect / Add Server.', 'Enter IP Address, SSH Port, Username and Password or Private Key authentication details.', 'Enter SNMPv3 username, auth protocol, auth password, privacy protocol and privacy password.', 'Select Validate SSH and review the result.', 'Select Validate SNMPv3 and review the result.', 'Review detected hostname, OS, architecture, interfaces, disks and warnings.', 'Select Add Validated Server only after both validations succeed.'], body: 'The visible UI validates SSH and SNMPv3 separately. A combined backend detection endpoint exists, but the frontend detect function is not connected to a visible button.' },
  { title: 'Server list, Refresh and selection', body: 'The left panel lists saved servers with display name or hostname, IP address, OS and monitoring status. Select a server to load its details. Refresh reloads the server list, scheduler status, retention status, current metrics, history, security events and thresholds. Automatic refresh runs every three minutes while a server is selected.' },
  { title: 'Start and Stop Monitoring', steps: ['Select a saved server.', 'Select Start Monitoring and provide the SNMPv3 credentials requested by the dialog.', 'Confirm the status becomes RUNNING and wait for the first successful poll.', 'Use Stop Monitoring to disable the scheduler task when authorized.'], warning: 'Monitoring uses SNMPv3 traffic and runs every three minutes. Stop Monitoring disables collection; it does not delete existing history.' },
  { title: 'Edit and Delete Server', body: 'Edit exposes IP address, SSH port and display name, then saves through the Linux server update API. Delete requires browser confirmation, stops the in-process monitoring task, and deletes the Linux server record. Cascading relationships remove Linux credentials, monitoring configuration, thresholds, current metrics, historical samples, interfaces, disks and security events.' },
  { title: 'Current metrics', body: 'CPU and Memory are percentages derived from SNMP OIDs. Swap and Disk are utilization percentages. Disk Read and Disk Write are counter-delta rates in bytes per second. Network RX and Network TX are interface counter-delta rates in bytes per second. Packets/sec, Errors and Drops are rates derived from interface counters. Load Average shows 1-minute, 5-minute and 15-minute values. Uptime is collected from sysUpTime and displayed in days.' },
  { title: 'Metric details and historical charts', body: 'Click CPU to view per-core values; Memory and Swap show a short explanation; Disk I/O shows read/write rates; Network shows RX/TX, packets and errors/drops; Load Average shows 1m/5m/15m values. CPU, Memory/Swap, Disk and Network Throughput charts use stored samples from the last 24 hours. There is no user-selectable time filter. Disk and Uptime cards are clickable but do not have dedicated detail panels in the current UI.' },
  { title: 'Threshold Settings', body: 'CPU, Memory and Disk each have Warning and Critical percentages. Defaults are 80% warning and 95% critical. Values must be between 0 and 100, and warning must be lower than critical. Enable threshold monitoring before selecting Save Thresholds. Thresholds are evaluated after successful samples.' },
  { title: 'Alerts, deduplication and recovery', body: 'A warning or critical alert is created when a collected CPU, memory or disk value reaches the configured threshold. An existing active alert of the same severity is not duplicated. A severity change resolves the previous alert and creates a new one. A normal successful sample resolves the active alert. Unavailable metrics are not treated as recovery. Email delivery uses shared alerting behavior and has not been separately verified for Linux alerts.' },
  { title: 'Security Events', body: 'Security Events displays firewall/security-log events collected over SSH, including time, type, severity, source, destination and port. Collect Security Logs opens a form for SSH username, password or private-key path. The endpoint retains and displays only the last 24 hours and the UI paginates 10 events per page. Normal SNMP traffic is not treated as a security event.' },
  { title: 'Monitoring architecture and retry behavior', body: 'The dedicated Linux scheduler runs an SNMPv3 collection task for each enabled server every 180 seconds. A failed cycle is retried once after two seconds. If both attempts fail, the status becomes FAILED and the last error is shown; the task remains available for the next cycle. Successful samples update both the current-metric row and the historical sample table.' },
  { title: 'History retention', body: 'Metric samples and security events older than 24 hours are deleted by a scheduler cleanup task that runs every 15 minutes. Current metrics are not retention-cleaned. Deleting a Linux server permanently cascades into its monitoring records; re-adding the server does not restore deleted history.' },
  { title: 'Permissions and site visibility', body: 'The route and read APIs use linux_servers:read. Adding requires linux_servers:create. Editing, starting or stopping monitoring, threshold changes, metric collection and security-log collection require linux_servers:update. Deleting requires linux_servers:delete. Start/stop and threshold endpoints explicitly check site access. Several list, detail, metric, history, security, edit and delete endpoints do not visibly apply the same site-access check; full site isolation is therefore not enforced consistently and requires remediation.' },
  { title: 'Troubleshooting', body: 'SNMP authentication failure: verify the v3 username, auth protocol/password, privacy protocol/password, security level and UDP 161 access. Host unreachable: verify IP, SSH port, routing and firewall rules. Missing metrics: check SNMP views for IF-MIB, HOST-RESOURCES-MIB, UCD-SNMP-MIB and DISKIO data. Stale data: review Last successful poll, Last run, Last seen and the monitoring error. Incorrect threshold alerts: confirm thresholds are enabled, ordered correctly and that the metric is available.' },
  { title: 'Known limitations and FAQs', faqs: [['Does NMS create the Linux SNMP user?', 'No. Configure the Linux account and SNMPv3 user on the host first.'], ['Is SNMPv2c recurring monitoring supported?', 'No verified recurring SNMPv2c support exists. The current UI and collector use SNMPv3.'], ['Are process and service panels available?', 'No. A collect_processes configuration field exists, but process/service monitoring is not implemented in the current page.'], ['Does Stop Monitoring delete history?', 'No. It disables collection without deleting samples.'], ['Does Delete Server preserve history?', 'No. Deletion cascades into Linux monitoring history and related records.'], ['Are Linux threshold email notifications verified?', 'No. Shared alerting is used, but Linux-specific email delivery was not separately verified.']] },
  { title: 'Important warning — history loss', warning: 'Deleting a Linux server permanently deletes associated Linux monitoring history and related records. Re-adding the same server does not restore deleted metrics, security events or monitoring configuration.' },
  { title: 'PDF actions', body: 'Use View PDF to open the approved Linux Server Monitoring User Guide in a new tab. Use Download PDF to save it as AgniGate_NMS_Linux_Server_Monitoring_User_Guide.pdf.' },
]

const remoteAccessSections: Section[] = [
  { title: 'Remote Access overview', body: 'Remote Access opens an authenticated terminal session to a device already available in NMS. The page supports SSH and Telnet, connection testing, SSH host-key handling, browser terminal tabs, active sessions and session history. Actions contact the selected device; use them only when authorized.' },
  { title: 'SSH and Telnet', body: 'SSH is encrypted and is the preferred protocol. Telnet is unencrypted and should be used only on a trusted network where it is explicitly allowed. The default ports are SSH 22 and Telnet 23, with a custom port option available. The selected protocol controls the default port; it does not change the device configuration.' },
  { title: 'Requirements and device selection', steps: ['Open Remote Access from the authenticated NMS sidebar.', 'Select an existing device from the device list. If an authorized device is not yet in inventory, use the page’s Add Device form with a device name and IP address.', 'Choose SSH or Telnet, confirm the host address shown from the selected device and verify the port.', 'Enter the authorized username and password. Never paste credentials into documentation or share them with other users.'] },
  { title: 'Remember Credential', body: 'Remember Credential is sent with Test Connection and session creation. Saving a credential requires the separate remote_access:manage_credentials permission; the inspected frontend does not expose a selected saved credential in the current form, so do not assume a password has been stored merely because the option is selected.' },
  { title: 'Test Connection', steps: ['Select the device and protocol, confirm the port and enter credentials when required.', 'Select TEST CONNECTION. NMS calls the remote-access test endpoint and reports success or a specific failure.', 'For an unknown SSH host key, review the fingerprint and use the trust action only after independently verifying the device. For a mismatch, stop and investigate before replacing the trusted key.', 'Retest after correcting credentials, routing, firewall or host-key configuration. Testing contacts the target device and is not a local-only validation.'] },
  { title: 'Connect Terminal', steps: ['After the required fields are valid, select CONNECT TERMINAL.', 'NMS creates a durable remote-access session and opens a browser WebSocket terminal for that session.', 'Use the terminal only for approved commands. Select the active terminal tab to return to a session and use the page disconnect control when finished.', 'A device can have only one active or connecting tab in the page; attempting another connection shows that it is already connected.'] },
  { title: 'Terminal interface and controls', body: 'The terminal uses an xterm-based browser interface. Sessions have status, protocol, port, device and elapsed-time information. Terminal input is sent through the authenticated WebSocket to the real remote session. The page can fit the terminal and toggle the terminal panel/fullscreen controls shown by the UI; these controls change presentation, not device state.' },
  { title: 'New Session and Active Sessions', body: 'New Session starts another connection workflow after selecting a different device or after disconnecting the current one. Active Sessions are restored from the backend active-session endpoint when the page loads, and the UI prevents duplicate connections for the same device. Session visibility is restricted by the session-view permission and the current user’s records.' },
  { title: 'Session History', body: 'Session History is loaded from the backend history endpoint and refreshed periodically while devices are available. It records session identity, device, protocol, start/end times, status, disconnect reason and available source/device details. History is durable session metadata; it does not expose terminal passwords. A browser refresh or route change does not automatically mean the remote session was destroyed, but backend-owned transports cannot survive a backend process restart.' },
  { title: 'SSH host-key trust and verification', body: 'SSH host keys are scanned, trusted and revoked through protected host-key actions. HOST_KEY_UNKNOWN requires an explicit trust decision; HOST_KEY_MISMATCH requires investigation and confirmation before replacing the stored key. Do not trust a key solely because the connection is convenient. Host-key management requires remote_access:manage_credentials.' },
  { title: 'WebSocket reconnection and persistence', body: 'The browser attaches to a created session through a bearer-authenticated WebSocket. The page reuses an open socket and refreshes history after terminal closure; a lost transport is shown as a connection error and the user can start a new session. Backend session records are durable, while the live adapter is process-owned, so service restart reconciliation disconnects sessions rather than preserving a live terminal.' },
  { title: 'Permissions and auditability', body: 'The route requires remote_access:view. Creating or connecting a session and attaching the terminal require remote_access:connect. Test Connection requires remote_access:test. Active-session and history viewing require remote_access:view_sessions. Remembering credentials and managing SSH host keys require remote_access:manage_credentials; disconnecting a session requires remote_access:disconnect. Credential create/update/delete actions write audit events. Site visibility is checked for credential/device access in the inspected backend; verify deployment-specific role assignments before granting access.' },
  { title: 'Important security warnings', warning: 'SSH is encrypted; Telnet is unencrypted. Use Telnet only on trusted networks where explicitly allowed. Never share passwords or credentials. Verify SSH host keys before trusting a device. Commands executed in the terminal affect the actual connected device. Avoid destructive commands unless authorized.' },
  { title: 'Troubleshooting', body: 'Device unavailable: confirm the device exists in NMS, the address and port are correct, routing/firewall rules allow the protocol and the remote service is listening. Authentication failed: verify username, password and protocol. SSH host-key unknown or mismatch: verify the fingerprint out of band and use trust/revoke only with authorization. WebSocket failed: confirm the session was created, the user has connect permission and the backend session service is available. Session disconnected: review the displayed reason, idle timeout or transport status, then start a new session.' },
  { title: 'Known limitations and FAQs', faqs: [['Does Test Connection open a terminal?', 'No. It validates the connection; Connect Terminal creates the interactive session.'], ['Does Telnet encrypt credentials or commands?', 'No. Telnet is unencrypted.'], ['Can multiple sessions use the same device?', 'The page prevents duplicate active/connecting sessions for the same device.'], ['Does a backend restart preserve an interactive terminal?', 'No. Durable records are reconciled as disconnected because the live transport is process-owned.'], ['Can I trust every SSH host-key prompt?', 'No. Verify the fingerprint independently before trusting or replacing a key.'], ['Are terminal commands simulated?', 'No. Commands are sent to the connected device.']] },
  { title: 'PDF actions', body: 'Use View PDF to open the approved Remote Access User Guide in a new tab. Use Download PDF to save it as AgniGate_NMS_Remote_Access_User_Guide.pdf.' },
]

const alertManagementSections: Section[] = [
  { title: 'Alert Management overview', body: 'Alert Management lists stored operational alerts associated with devices or Linux servers. It shows the current alert count, severity, title, device, status, creation time and available actions. The page is protected by the alerts:read permission and does not itself run a live probe.' },
  { title: 'Severity and status', body: 'The UI displays critical, high, warning and info severities. Alert status values are open, acknowledged and resolved. Severity describes importance; status describes lifecycle state. The list is ordered by newest created time from the backend, while the visible count is the number returned for the selected status request, subject to the API limit.' },
  { title: 'Search, status filter and pagination', steps: ['Use the status selector to choose All Status, Open, Acknowledged or Resolved. Changing it reloads the matching server-side result set.', 'Use Search to filter the loaded results by title, description or severity. Search is client-side over the returned list.', 'Use the table pagination controls to move through the currently filtered list. The frontend does not request another page from the API for each table page; the API response is limited to the requested result window.', 'Use the alert count and table fields to confirm that the result is the intended alert before taking action.'] },
  { title: 'Alert details and event history', body: 'Select SHOW on a row to open the alert detail panel. The detail view shows the selected alert’s title, description, severity, status, device association, timestamps and acknowledgement/resolution fields exposed by the record. Full event history is not a separate alert-history API in the inspected page; related operational events are maintained by the backend event/audit flows and should not be assumed to be a complete packet-by-packet history.' },
  { title: 'Acknowledge workflow', steps: ['Find an open alert and select ACK when you are authorized to take ownership of the notification.', 'NMS calls POST /alerts/{id}/acknowledge with the alert ID.', 'The backend changes status to acknowledged, records the current user as acknowledged_by and writes an audit event.', 'The page reloads the list and shows the updated status. Backend permission required: alerts:update.'] },
  { title: 'Resolve workflow and recovery', steps: ['Investigate the underlying condition before resolving an alert.', 'Select RESOLVE on an open or acknowledged alert.', 'NMS calls POST /alerts/{id}/resolve. The backend sets status to resolved and records resolved_at.', 'The backend also invokes incident recovery processing and writes an audit event. Automatic recovery is separate: polling/threshold services can resolve a verified active alert when a healthy result is received.'] },
  { title: 'New and Edit Alert', body: 'Users with alerts:create see the New button. The form accepts an optional device, severity, title, description and status, with title required. Saving calls POST /alerts and may create notification rows for open/acknowledged alerts. Users with alerts:update can edit those fields through PATCH /alerts/{id}; resolving an edited alert also invokes recovery processing. Validation and API errors are shown as toast messages.' },
  { title: 'Delete Alert', body: 'Users with alerts:delete can use the row Delete action after a confirmation dialog. The backend soft-deletes the alert by setting deleted_at and records an audit event; deleted alerts are excluded from normal listing. A global clear-all endpoint exists but requires both alerts:delete and Super Admin authorization and is not a normal page workflow.' },
  { title: 'Threshold-generated alerts and deduplication', body: 'SNMP polling evaluates supported CPU, memory, storage, interface and availability conditions and can create threshold or unavailable alerts. The alerting service keeps one active alert for the same condition/device instead of creating duplicates. When a verified value returns below the recovery condition, the active alert is resolved and a recovery notification path is used. Exact thresholds depend on the module configuration; Alert Management itself does not configure thresholds.' },
  { title: 'Device association and access scope', body: 'An alert may reference a device, Linux server or interface. Device-scoped alerts are checked against the current user’s accessible sites. Device-less operational alerts can remain visible because the backend intentionally retains them. The route uses alerts:read; create, update, delete, acknowledge and resolve use alerts:create, alerts:update or alerts:delete as appropriate. Site isolation is enforced for device/Linux-server scoped alert access by the inspected alert routes; live deployment role assignments still require verification.' },
  { title: 'Notifications and email', body: 'Creating or automatically generating an open/acknowledged alert can create notification records and use the shared notification delivery path. Email delivery depends on configured recipients and SMTP/provider state. The Alert Management page does not prove that an email was delivered; check Notifications and delivery status separately.' },
  { title: 'Refresh behavior and limitations', body: 'The page loads alerts and device options when opened and reloads after create, edit, acknowledge, resolve or delete. No dedicated refresh button or automatic polling loop is implemented in the inspected page. The API caps a single list request at 500 records, while the frontend’s default request uses the API default window; older alerts may therefore require a different reporting or API view.' },
  { title: 'Important warnings', warning: 'Deleting a device may permanently remove its monitoring history. Re-adding the device does not automatically restore previous historical records. Do not delete alerts without authorization: deletion hides the alert from normal listings and can affect operational investigation, audit context and incident review. Acknowledge or resolve only after following your organization’s incident procedure.' },
  { title: 'Troubleshooting and FAQs', faqs: [['Why is an alert missing?', 'Check the selected status filter, search text, pagination, site access and the API result window. Device-less alerts and deleted alerts follow separate backend rules.'], ['Does Acknowledge clear the alert?', 'No. It changes the lifecycle status to acknowledged; it does not prove the underlying condition is fixed.'], ['Does Resolve delete the alert?', 'No. It marks the alert resolved and records a recovery timestamp.'], ['Are duplicate threshold alerts created every poll?', 'The alerting service attempts to keep one active alert for the same device/condition. Verify the specific module and condition if duplicates appear.'], ['Does creating an alert guarantee email delivery?', 'No. Notification creation and provider delivery are separate; email delivery requires configured recipients and a working provider.'], ['Can Alert Management test a device?', 'No. This page reads and manages alert records; it does not perform device discovery or live probes.']] },
  { title: 'PDF actions', body: 'Use View PDF to open the approved Alert Management User Guide in a new tab. Use Download PDF to save it as AgniGate_NMS_Alert_Management_User_Guide.pdf.' },
]

const eventsSections: Section[] = [
  { title: 'Events overview', body: 'Events records describe operational activity associated with NMS devices. The Events page loads event records and device options, displays the event count, and provides controlled create, edit and delete workflows. It does not itself start discovery, polling or monitoring.' },
  { title: 'Event types and device association', body: 'Each event has an event type, optional description, timestamp and optional device association. Device names are resolved from the loaded device options. Events may also be created by other NMS workflows, so the page should be treated as a record viewer and manager rather than the only source of events.' },
  { title: 'Listing, search and pagination', steps: ['Open Events from the authenticated NMS sidebar.', 'Review the event table and use the search field to filter the loaded records by event type, description or device text as supported by the page.', 'Use the pagination controls to move through the current result set. The page uses the shared table pagination behavior; the backend list endpoint supports skip and limit.', 'Review the timestamp and associated device before opening an edit or delete action.'] },
  { title: 'New Event workflow', steps: ['Select NEW when your role has events:create permission.', 'Choose an optional device association, enter the event type and add a description when needed.', 'Submit the form after checking the values. The frontend calls POST /events.', 'On success the page reloads the event list; validation or API failures are shown as an error notification.'] },
  { title: 'Edit Event workflow', steps: ['Select EDIT for the event you are authorized to change.', 'Review and update the device association, event type or description in the form.', 'Submit the form. The frontend calls PATCH /events/{id}.', 'The page reloads the list after a successful response and reports failures without changing the local record.'] },
  { title: 'Delete Event workflow', body: 'Select DELETE only after confirming that the event may be removed. The page shows a danger confirmation before calling DELETE /events/{id}. The backend applies the event CRUD deletion behavior and records the deletion audit action. Deletion is not a way to clear a search filter or hide an unresolved operational problem.' },
  { title: 'Permissions and site access', body: 'Viewing and retrieving events requires events:read. Creating requires events:create, editing requires events:update and deleting requires events:delete. The inspected Events endpoints use permission checks. The event list endpoint itself applies the events:read check; event-specific site isolation should be confirmed against the deployed authorization policy before treating an event as visible across all sites.' },
  { title: 'Retention and known limitations', body: 'The Events page does not expose a dedicated retention setting, export action or live refresh control in the inspected implementation. The API list supports skip and limit and excludes soft-deleted records. Exact cleanup timing and whether every event producer applies the same site scope are not established by the inspected page alone.' },
  { title: 'Troubleshooting and FAQs', faqs: [['Why is an event missing?', 'Check permissions, pagination, the search text, device association and whether the record was deleted or outside the API result window.'], ['Does creating an event contact a device?', 'No. Creating an event writes an event record; it does not run discovery or a network probe.'], ['Can I edit system-generated events?', 'The UI exposes an edit workflow, but authorization and operational policy should determine whether a generated record may be changed.'], ['Does deleting an event remove device monitoring?', 'No event deletion is separate from device monitoring. Do not use it to change device state.'], ['Is event history retained forever?', 'No retention duration is confirmed by the inspected page and routes; consult the deployed data-retention policy.']] },
  { title: 'Important warning — event history deletion', warning: 'Deleting an event can permanently remove that event from normal history views. Confirm authorization, retention requirements and incident/audit needs before deleting event records. Deleting an event does not repair the underlying device condition and should never be used as a substitute for resolving it.' },
  { title: 'PDF actions', body: 'Use View PDF to open the approved Events User Guide in a new tab. Use Download PDF to save it as AgniGate_NMS_Events_User_Guide.pdf.' },
]

const notificationsSections: Section[] = [
  { title: 'Notifications overview', body: 'The Notifications page at Management > Notifications displays notification records with their channel, recipient, linked alert, status, sent time and available actions. Authorized users can search, create, edit and delete records. Automatic alert emails are handled separately by the backend alerting service.' },
  { title: 'Route and RBAC permissions', body: 'Open /notifications from Management > Notifications. Viewing requires notifications:read. Creating requires notifications:create, editing requires notifications:update, and deleting requires notifications:delete. These permissions are enforced by the backend API, so New, Edit and Delete controls may not be visible for every role.' },
  { title: 'Notification table and columns', body: 'Channel identifies the method, such as email. Sent To is the recipient address or destination. Alert shows the linked alert title or a dash when no alert is linked or the alert is unavailable. Status records a state such as pending, delivered or failed. Sent At shows the recorded send time when available. Actions contain Edit and Delete controls according to permission.' },
  { title: 'Search and pagination', body: 'Search filters currently loaded rows by channel, recipient or status. Pagination moves through the loaded table rows; changing pages does not retrieve additional backend pages. Large notification histories may therefore not be fully visible.' },
  { title: 'Alert association', body: 'A notification may reference an alert. The UI loads up to 50 alerts separately to resolve alert titles, so older or unavailable linked alerts can display a dash even when an alert ID exists.' },
  { title: 'New Notification workflow', steps: ['Select + New if your role has notifications:create.', 'Optionally choose an alert association.', 'Select Email, SMS, Slack or Webhook.', 'Enter a non-blank Sent To destination.', 'Review the initial pending status and save.'], warning: 'Creating a notification record does not automatically send an email, SMS, Slack message or webhook. It is a database CRUD action.' },
  { title: 'Edit workflow', body: 'Select the pencil icon for an existing row, adjust the available fields and save. The backend supports changes to channel, recipient, status and sent timestamp. Editing a status is not equivalent to actually delivering a message.' },
  { title: 'Delete workflow and history warning', body: 'Select the trash icon and review the danger confirmation before proceeding. Delete requires notifications:delete. Deleting a record is not a way to cancel an email already handed to SMTP.', warning: 'Deleting notification records may permanently remove important history. Do not delete records needed for investigations, compliance or incident history.' },
  { title: 'Channels and verified limitations', body: 'Email: backend SMTP sending exists for automatic alert notifications. SMS, Slack and Webhook: selectable in the New form, but working delivery integrations were not verified. Do not treat these options as production delivery guarantees.' },
  { title: 'Pending, delivered and failed statuses', body: 'pending means no completed send is recorded; automatic alert email service can use it when SMTP is not configured. delivered means SMTP send_message() completed without an exception, not that the recipient inbox received the message. failed means an exception occurred while sending. sent is a frontend-recognized label; automatic backend email delivery commonly records delivered.' },
  { title: 'Automatic alert-triggered emails', body: 'The backend alerting service can generate emails for device-down, device-added, threshold, SNMP-unavailable, operational and recovery events. Alert-level deduplication exists for active conditions; a general notification deduplication mechanism was not verified.' },
  { title: 'SMTP configuration requirements', body: 'Automatic email sending depends on a server-side SMTP host, port, optional credentials, TLS setting, sender address and configured alert recipients. The service builds plain-text/HTML messages and calls SMTP send_message(). Credentials are configured server-side and are not exposed by the Notifications page.' },
  { title: 'Troubleshooting and FAQs', faqs: [['Why is a notification pending?', 'SMTP may be unconfigured, or the record may have been manually created rather than sent.'], ['Why does delivered appear but no email arrived?', 'SMTP client success does not establish inbox delivery. Check the recipient address, spam folder and mail-provider logs with an administrator.'], ['Why is the Alert column blank?', 'The alert may be unlinked or outside the 50-alert subset loaded for display.'], ['Can I retry a failed email here?', 'No manual retry action was verified.'], ['Do SMS, Slack or Webhook selections send messages?', 'Delivery support for those channels was not verified.'], ['Why are New, Edit or Delete unavailable?', 'Your role may lack the required permission.']] },
  { title: 'Site isolation and retention limitations', body: 'No notification-specific site filtering or retention cleanup policy was verified. Recipient-level delivery confirmation, bounce tracking, a general automatic retry queue and manual retry control were also not verified. Recipient addresses are visible to authorized notification readers; limit access appropriately.' },
  { title: 'Important operational warnings', warning: 'Notification-specific site isolation is unverified. Do not edit notification statuses to misrepresent actual delivery. This guide documents inspected behavior; it is not a live email-delivery or security-certification report.' },
]

const guideContent: Record<string, Section[]> = {
  Overview: overviewSections,
  Topology: topologySections,
  'IP Scan': ipScanSections,
  'All Devices': allDevicesSections,
  'Windows Devices': windowsSections,
  'SNMP Devices': snmpSections,
  'Device Monitoring': deviceMonitoringSections,
  'Packet Analysis': packetAnalysisSections,
  'Linux Server Monitoring': linuxSections,
  'Report Center': reportSections,
  'Remote Access': remoteAccessSections,
  'Alert Management': alertManagementSections,
  Events: eventsSections,
  Notifications: notificationsSections,
}

/* =====================================================================
   Shared UI pieces
   ===================================================================== */

const accentStyle = {
  color: 'var(--t-accent)',
  border: '1px solid var(--t-accent-border)',
  background: 'var(--t-accent-alpha)',
} as const

const btnClass =
  'inline-flex items-center rounded-lg px-3 py-2 font-mono text-[11px] transition-opacity hover:opacity-80 focus-visible:outline focus-visible:outline-2 disabled:cursor-not-allowed disabled:opacity-50'

function ActionButton({ children, onClick, disabled = false }: { children: string; onClick?: () => void; disabled?: boolean }) {
  return (
    <button type="button" disabled={disabled} onClick={onClick} className={btnClass} style={accentStyle}>
      {children}
    </button>
  )
}

// Link styled as a button (avoids invalid <a><button/></a> nesting)
function ActionLink({ href, download, children }: { href: string; download: string; children: string }) {
  return (
    <a href={href} download={download} className={btnClass} style={accentStyle}>
      {children}
    </a>
  )
}

function StatusBadge({ available }: { available: boolean }) {
  return (
    <span
      className="rounded-full px-2 py-1 font-mono text-[10px]"
      style={{
        color: available ? '#43e6a3' : 'var(--t-muted)',
        background: available ? 'rgb(67 230 163 / 12%)' : 'var(--t-bg)',
      }}
    >
      {available ? 'Available' : 'Coming Soon'}
    </span>
  )
}

function GuideIcon({ path }: { path: string }) {
  return (
    <div className="flex h-10 w-10 items-center justify-center rounded-lg" style={{ color: 'var(--t-accent)', background: 'var(--t-accent-alpha)' }}>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d={path} />
      </svg>
    </div>
  )
}

/* =====================================================================
   Guide detail
   ===================================================================== */

// Same bold-warning behaviour as the original implementation
const BOLD_WARNING_GUIDES = ['Device Monitoring', 'Packet Analysis', 'Linux Server Monitoring', 'Report Center', 'Remote Access', 'Alert Management', 'Events']

const isBoldWarning = (guideName: string, title: string) =>
  (guideName === 'SNMP Devices' && title === 'Deletion warning') ||
  (BOLD_WARNING_GUIDES.includes(guideName) && title.startsWith('Important'))

function highlight(text: string, query: string) {
  const q = query.trim()
  if (!q) return text
  const escaped = q.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return text.split(new RegExp(`(${escaped})`, 'gi')).map((part, i) =>
    part.toLowerCase() === q.toLowerCase() ? (
      <mark key={i} className="rounded px-0.5" style={{ background: 'color-mix(in srgb, var(--t-accent) 30%, transparent)', color: 'inherit' }}>
        {part}
      </mark>
    ) : (
      part
    ),
  )
}

function sectionText(s: Section) {
  return [s.title, s.body, ...(s.steps ?? []), s.warning, ...(s.faqs ?? []).flat()].filter(Boolean).join(' ').toLowerCase()
}

function SectionCard({ section, id, query, bold }: { section: Section; id: string; query: string; bold: boolean }) {
  return (
    <div id={id} className="scroll-mt-24">
      <GlassCard>
        <div className="p-5">
          <h2 className="font-display text-sm font-semibold">{highlight(section.title, query)}</h2>

          {section.body && (
            <p className="mt-3 whitespace-pre-line font-mono text-xs leading-6" style={{ color: 'var(--t-muted)' }}>
              {highlight(section.body, query)}
            </p>
          )}

          {section.steps && (
            <ol className="mt-3 space-y-2 font-mono text-xs leading-5" style={{ color: 'var(--t-muted)' }}>
              {section.steps.map((step, i) => (
                <li key={i} className="flex gap-2">
                  <span className="shrink-0" style={{ color: 'var(--t-accent)' }}>{i + 1}.</span>
                  <span>{highlight(step, query)}</span>
                </li>
              ))}
            </ol>
          )}

          {section.warning && (
            <div
              role="note"
              className={`mt-3 whitespace-pre-line rounded-lg p-3 font-mono text-xs leading-5 ${bold ? 'font-bold' : ''}`}
              style={{ color: '#b45309', background: 'color-mix(in srgb, #f59e0b 12%, transparent)', border: '1px solid color-mix(in srgb, #f59e0b 40%, transparent)' }}
            >
              {section.warning}
            </div>
          )}

          {section.faqs && (
            <div className="mt-3 space-y-2">
              {section.faqs.map(([q, a], i) => (
                <details key={i} className="rounded-lg p-3 font-mono text-xs" style={{ color: 'var(--t-muted)', border: '1px solid var(--t-border)' }}>
                  <summary className="cursor-pointer" style={{ color: 'var(--t-text)' }}>{highlight(q, query)}</summary>
                  <p className="mt-2 leading-5">{highlight(a, query)}</p>
                </details>
              ))}
            </div>
          )}
        </div>
      </GlassCard>
    </div>
  )
}

function GuideDetail({ guide, onBack }: { guide: Guide; onBack: () => void }) {
  const [query, setQuery] = useState('')
  const sections = guideContent[guide.name]

  useEffect(() => {
    window.scrollTo({ top: 0 })
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onBack()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onBack])

  const visible = useMemo(() => {
    if (!sections) return []
    const q = query.toLowerCase().trim()
    return sections.map((s, index) => ({ s, index })).filter(({ s }) => !q || sectionText(s).includes(q))
  }, [sections, query])

  const jumpTo = (index: number) =>
    document.getElementById(`sec-${index}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })

  return (
    <div className="space-y-5 p-4 md:p-6">
      <button type="button" onClick={onBack} className="font-mono text-xs" style={{ color: 'var(--t-accent)' }}>
        ← Back to Help Center
      </button>

      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="font-display text-2xl font-bold tracking-widest">{guide.name.toUpperCase()} GUIDE</h1>
          <p className="mt-1 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>
            {guide.description ?? 'Documentation in progress.'}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {guide.pdf ? (
            <>
              <ActionButton onClick={() => window.open(guide.pdf, '_blank', 'noopener,noreferrer')}>View PDF</ActionButton>
              <ActionLink href={guide.pdf} download={guide.downloadName ?? ''}>Download PDF</ActionLink>
            </>
          ) : (
            <StatusBadge available={false} />
          )}
        </div>
      </header>

      {sections ? (
        <>
          <input
            aria-label="Search in this guide"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={`Search inside ${guide.name} guide…`}
            className="w-full max-w-xl rounded-xl px-4 py-3 font-mono text-xs outline-none"
            style={{ color: 'var(--t-text)', background: 'var(--t-card)', border: '1px solid var(--t-border)' }}
          />

          <div className="grid gap-5 lg:grid-cols-[220px_1fr]">
            <nav aria-label="Guide contents" className="hidden lg:block">
              <div className="sticky top-4 max-h-[80vh] space-y-1 overflow-y-auto pr-2">
                <p className="mb-2 font-mono text-[10px] uppercase tracking-widest" style={{ color: 'var(--t-muted)' }}>Contents</p>
                {visible.map(({ s, index }) => (
                  <button
                    key={index}
                    type="button"
                    onClick={() => jumpTo(index)}
                    className="block w-full truncate rounded-md px-2 py-1.5 text-left font-mono text-[11px] transition-opacity hover:opacity-80"
                    style={{ color: 'var(--t-muted)' }}
                  >
                    {s.title}
                  </button>
                ))}
              </div>
            </nav>

            {visible.length ? (
              <div className="grid content-start gap-4 md:grid-cols-2">
                {visible.map(({ s, index }) => (
                  <SectionCard key={index} id={`sec-${index}`} section={s} query={query} bold={isBoldWarning(guide.name, s.title)} />
                ))}
              </div>
            ) : (
              <GlassCard>
                <div className="p-10 text-center font-mono text-xs" style={{ color: 'var(--t-muted)' }}>
                  No sections match “{query}”.
                </div>
              </GlassCard>
            )}
          </div>
        </>
      ) : (
        <GlassCard>
          <div className="p-10 text-center">
            <p className="font-display text-sm font-semibold">Documentation in progress</p>
            <p className="mt-2 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>This guide will be available soon.</p>
          </div>
        </GlassCard>
      )}
    </div>
  )
}

/* =====================================================================
   Help Center (list page)
   ===================================================================== */

export default function HelpCenter() {
  const [search, setSearch] = useState('')
  const [category, setCategory] = useState<'All' | Category>('All')
  const [selected, setSelected] = useState<Guide | null>(null)

  const filtered = useMemo(() => {
    const q = search.toLowerCase().trim()
    return guides.filter(
      (g) =>
        (category === 'All' || g.category === category) &&
        (!q || g.name.toLowerCase().includes(q) || (g.description ?? '').toLowerCase().includes(q)),
    )
  }, [search, category])

  const availableCount = guides.filter((g) => g.pdf).length

  if (selected) return <GuideDetail guide={selected} onBack={() => setSelected(null)} />

  return (
    <div className="space-y-6 p-4 md:p-6">
      <header>
        <h1 className="font-display text-2xl font-bold tracking-widest">AgniGate NMS Help Center</h1>
        <p className="mt-2 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>
          Explore module guides, learn features, and download user documentation.{' '}
          <span style={{ color: 'var(--t-accent)' }}>{availableCount} of {guides.length} guides available.</span>
        </p>
      </header>

      <div className="relative max-w-xl">
        <input
          aria-label="Search guides"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search guides by module name or topic"
          className="w-full rounded-xl px-4 py-3 font-mono text-xs outline-none"
          style={{ color: 'var(--t-text)', background: 'var(--t-card)', border: '1px solid var(--t-border)' }}
        />
        {search && (
          <button type="button" onClick={() => setSearch('')} className="absolute right-3 top-1/2 -translate-y-1/2 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>
            Clear
          </button>
        )}
      </div>

      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Guide categories">
        {categories.map((c) => {
          const active = c === category
          return (
            <button
              key={c}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setCategory(c)}
              className="rounded-full px-3 py-1.5 font-mono text-[11px] transition-opacity hover:opacity-80"
              style={active ? accentStyle : { color: 'var(--t-muted)', border: '1px solid var(--t-border)' }}
            >
              {c}
            </button>
          )
        })}
      </div>

      {filtered.length ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {filtered.map((guide) => (
            <GlassCard key={guide.name}>
              <div className="flex h-full flex-col p-5">
                <div className="flex items-start justify-between gap-3">
                  <GuideIcon path={guide.icon} />
                  <StatusBadge available={Boolean(guide.pdf)} />
                </div>
                <h2 className="mt-4 font-display text-base font-semibold">{guide.name}</h2>
                <p className="mt-1 font-mono text-[10px] uppercase tracking-widest" style={{ color: 'var(--t-muted)' }}>{guide.category}</p>
                <p className="mt-2 min-h-12 font-mono text-xs leading-5" style={{ color: 'var(--t-muted)' }}>
                  {guide.description ?? 'Documentation in progress.'}
                </p>
                <div className="mt-auto flex flex-wrap gap-2 pt-5">
                  {guide.pdf ? (
                    <>
                      <ActionButton onClick={() => setSelected(guide)}>Read Guide</ActionButton>
                      <ActionButton onClick={() => window.open(guide.pdf, '_blank', 'noopener,noreferrer')}>View PDF</ActionButton>
                      <ActionLink href={guide.pdf} download={guide.downloadName ?? ''}>Download PDF</ActionLink>
                    </>
                  ) : (
                    <ActionButton disabled>Guide Coming Soon</ActionButton>
                  )}
                </div>
              </div>
            </GlassCard>
          ))}
        </div>
      ) : (
        <GlassCard>
          <div className="p-10 text-center">
            <p className="font-display text-sm font-semibold">No guides found</p>
            <p className="mt-2 font-mono text-xs" style={{ color: 'var(--t-muted)' }}>Try a different module name or category.</p>
          </div>
        </GlassCard>
      )}
    </div>
  )
}
