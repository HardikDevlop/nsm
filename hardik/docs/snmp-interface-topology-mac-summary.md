# SNMP Interface, Network Topology, and MAC Table

This document describes the data contract used by the three SNMP views.

## 1. Interfaces

The interface collector reads IF-MIB counters and status values from the
device. The scheduler stores the latest successful sample in the latest
interface tables and keeps history for rate calculations.

- Source: `ifIndex`, `ifName`, description, speed, admin/oper status, octets,
  packets, errors, and discards.
- UI: `/snmp/devices/{device_id}/interfaces` and the Interfaces module page.
- Refresh: the browser uses that module's monitoring configuration. If the
  module is running at 60 seconds, the page refreshes every 60 seconds.
- Rates: RX/TX Mbps and packet/error rates are calculated from the previous
  counter sample and elapsed time. The first sample has no delta yet.
- Status: operational status is independent from traffic. A down interface
  can correctly show zero traffic while an up interface can show live rates.

## 2. Network Topology

Automatic topology is a connected-device graph, not a routing-table graph.

- Confirmed links come from LLDP/CDP neighbor evidence.
- Inferred endpoint links come from cleaned MAC-table port groups and ARP IP
  correlation.
- Routing next-hops are Layer-3 reachability information only. They are not
  rendered as physical links because a route does not prove a cable or switch
  port connection.
- The local switch/device is retained as the graph parent so its connected
  ports have context. Its own MAC is never rendered as a child endpoint.
- Multi-MAC aggregate groups remain visible in the graph. Their card uses the
  first resolved IP as the identity, or the first learned MAC when no IP is
  available; it never uses the label `PORT SUMMARY`.
- A self-reported LLDP neighbor is ignored when its IP, MAC, or hostname
  matches the local device.
- A topology refresh must not replace a newer persisted snapshot with an older
  response. The graph is rebuilt from the current inventory and cleaned port
  groups.

Primary views/endpoints:

- Global graph: `GET /snmp/topology`
- Explicit global refresh: `GET /snmp/topology?refresh=true`
- Per-device live graph: `GET /snmp/devices/{device_id}/device-topology`

## 3. MAC Table and Port Summary

The MAC table is collected from BRIDGE-MIB/Q-BRIDGE-MIB. Q-BRIDGE-MIB is used
when available so VLAN information is preserved.

- Entry identity: MAC address, bridge port, mapped ifIndex, VLAN, and FDB
  status.
- Port Summary: entries are grouped by switch port and expose MAC count, VLANs,
  MAC addresses, learned IP addresses, and classification.
- Classifications:
  - `ENDPOINT`: one learned MAC on the port.
  - `UNKNOWN`: multiple learned MACs without a confirmed uplink signal.
  - `UPLINK/TRUNK`: LLDP evidence identifies the port as an uplink/trunk.
- Self filtering: FDB entries with status `self` are discarded by the backend
  before `entries` and `port_groups` are returned. The UI also filters stale
  cached self entries as a defensive fallback.
- Therefore a port such as port 1 shows only learned remote addresses. The
  switch's own MAC cannot create a fake endpoint, CPU node, or topology link.

## Data flow

```text
SNMP walk
  -> MAC/ARP + interface + LLDP collectors
  -> remove FDB status=self
  -> persist latest successful module snapshot
  -> Port Summary groups
  -> Network Topology MAC/ARP endpoints
```

The Port Summary is the source of truth for inferred MAC/ARP topology. The
topology page must not independently recreate self entries or invent routing
connections.
