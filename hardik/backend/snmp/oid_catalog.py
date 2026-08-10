"""
Agnigate NMS — OID Catalog
===========================
Single source of truth for every OID the system knows about.

Design rules
------------
- Zero JSON / YAML / INI files. All OID knowledge is Python.
- Standard MIBs always take priority. Vendor OIDs are fallbacks.
- Adding a new vendor = adding entries to VENDOR_OID_CATALOG below.
- No OID string is ever hardcoded inside a collector. Collectors call
  OIDResolver.get(domain, metric) and get back whatever OID the device
  actually responded to.

Structure
---------
  STANDARD_OIDS           dict[str, str]
      Flat key → OID for standard MIBs (RFC-defined, IANA-registered).

  VENDOR_OID_CATALOG      dict[str, dict[str, dict[str, str]]]
      vendor_key → domain → metric → OID
      vendor_key matches VendorDetector.detect() return value.

  VENDOR_SYSOID_PREFIXES  dict[str, str]
      OID prefix string → vendor_key  (used for sysObjectID matching)

  VENDOR_DESCR_KEYWORDS   dict[str, list[str]]
      vendor_key → list of lowercase sysDescr keywords

  ENTITY_PHYSICAL_CLASS   dict[int, str]
  ENTITY_SENSOR_TYPE      dict[str, tuple[str, str]]
  HR_STORAGE_TYPES        dict[str, str]
  ROUTING_PROTOCOLS       dict[str, str]
  IF_ADMIN_STATUS         dict[str, str]
  IF_OPER_STATUS          dict[str, str]

Everything is importable and testable with plain `import`.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Standard MIBs
# ---------------------------------------------------------------------------

STANDARD_OIDS: dict[str, str] = {
    # SNMPv2-MIB system group
    "system.description":           "1.3.6.1.2.1.1.1.0",
    "system.object_id":             "1.3.6.1.2.1.1.2.0",
    "system.uptime":                "1.3.6.1.2.1.1.3.0",
    "system.contact":               "1.3.6.1.2.1.1.4.0",
    "system.name":                  "1.3.6.1.2.1.1.5.0",
    "system.location":              "1.3.6.1.2.1.1.6.0",
    "system.services":              "1.3.6.1.2.1.1.7.0",

    # HOST-RESOURCES-MIB (RFC 2790)
    "hrSystemUptime":               "1.3.6.1.2.1.25.1.1.0",
    "hrProcessorTable":             "1.3.6.1.2.1.25.3.3.1",
    "hrProcessorLoad":              "1.3.6.1.2.1.25.3.3.1.2",
    "hrStorageTable":               "1.3.6.1.2.1.25.2.3.1",
    "hrStorageIndex":               "1.3.6.1.2.1.25.2.3.1.1",
    "hrStorageType":                "1.3.6.1.2.1.25.2.3.1.2",
    "hrStorageDescr":               "1.3.6.1.2.1.25.2.3.1.3",
    "hrStorageAllocationUnits":     "1.3.6.1.2.1.25.2.3.1.4",
    "hrStorageSize":                "1.3.6.1.2.1.25.2.3.1.5",
    "hrStorageUsed":                "1.3.6.1.2.1.25.2.3.1.6",
    "hrStorageRam":                 "1.3.6.1.2.1.25.2.1.2",
    "hrStorageVirtualMemory":       "1.3.6.1.2.1.25.2.1.3",
    "hrStorageFixedDisk":           "1.3.6.1.2.1.25.2.1.4",

    # UCD-SNMP-MIB (Linux / net-snmp)
    "ucdCpuUser":                   "1.3.6.1.4.1.2021.11.9.0",
    "ucdCpuSystem":                 "1.3.6.1.4.1.2021.11.10.0",
    "ucdCpuIdle":                   "1.3.6.1.4.1.2021.11.11.0",
    "ucdCpuRawUser":                "1.3.6.1.4.1.2021.11.50.0",
    "ucdCpuRawNice":                "1.3.6.1.4.1.2021.11.51.0",
    "ucdCpuRawSystem":              "1.3.6.1.4.1.2021.11.52.0",
    "ucdCpuRawIdle":                "1.3.6.1.4.1.2021.11.53.0",
    "ucdLoadAvg1":                  "1.3.6.1.4.1.2021.10.1.5.1",
    "ucdLoadAvg5":                  "1.3.6.1.4.1.2021.10.1.5.2",
    "ucdLoadAvg15":                 "1.3.6.1.4.1.2021.10.1.5.3",
    "ucdMemTotalReal":              "1.3.6.1.4.1.2021.4.5.0",
    "ucdMemAvailReal":              "1.3.6.1.4.1.2021.4.6.0",
    "ucdMemTotalFree":              "1.3.6.1.4.1.2021.4.11.0",
    "ucdMemShared":                 "1.3.6.1.4.1.2021.4.13.0",
    "ucdMemBuffer":                 "1.3.6.1.4.1.2021.4.14.0",
    "ucdMemCached":                 "1.3.6.1.4.1.2021.4.15.0",
    "ucdMemTotalSwap":              "1.3.6.1.4.1.2021.4.3.0",
    "ucdMemAvailSwap":              "1.3.6.1.4.1.2021.4.4.0",

    # IF-MIB (RFC 2863)
    "ifTable":                      "1.3.6.1.2.1.2.2.1",
    "ifIndex":                      "1.3.6.1.2.1.2.2.1.1",
    "ifDescr":                      "1.3.6.1.2.1.2.2.1.2",
    "ifType":                       "1.3.6.1.2.1.2.2.1.3",
    "ifMtu":                        "1.3.6.1.2.1.2.2.1.4",
    "ifSpeed":                      "1.3.6.1.2.1.2.2.1.5",
    "ifPhysAddress":                "1.3.6.1.2.1.2.2.1.6",
    "ifAdminStatus":                "1.3.6.1.2.1.2.2.1.7",
    "ifOperStatus":                 "1.3.6.1.2.1.2.2.1.8",
    "ifLastChange":                 "1.3.6.1.2.1.2.2.1.9",
    "ifInOctets":                   "1.3.6.1.2.1.2.2.1.10",
    "ifInUcastPkts":                "1.3.6.1.2.1.2.2.1.11",
    "ifInNUcastPkts":               "1.3.6.1.2.1.2.2.1.12",
    "ifInDiscards":                 "1.3.6.1.2.1.2.2.1.13",
    "ifInErrors":                   "1.3.6.1.2.1.2.2.1.14",
    "ifInUnknownProtos":            "1.3.6.1.2.1.2.2.1.15",
    "ifOutOctets":                  "1.3.6.1.2.1.2.2.1.16",
    "ifOutUcastPkts":               "1.3.6.1.2.1.2.2.1.17",
    "ifOutNUcastPkts":              "1.3.6.1.2.1.2.2.1.18",
    "ifOutDiscards":                "1.3.6.1.2.1.2.2.1.19",
    "ifOutErrors":                  "1.3.6.1.2.1.2.2.1.20",

    # ifXTable (RFC 2863 extension — 64-bit counters)
    "ifXTable":                     "1.3.6.1.2.1.31.1.1.1",
    "ifName":                       "1.3.6.1.2.1.31.1.1.1.1",
    "ifInMulticastPkts":            "1.3.6.1.2.1.31.1.1.1.2",
    "ifInBroadcastPkts":            "1.3.6.1.2.1.31.1.1.1.3",
    "ifOutMulticastPkts":           "1.3.6.1.2.1.31.1.1.1.4",
    "ifOutBroadcastPkts":           "1.3.6.1.2.1.31.1.1.1.5",
    "ifHCInOctets":                 "1.3.6.1.2.1.31.1.1.1.6",
    "ifHCInUcastPkts":              "1.3.6.1.2.1.31.1.1.1.7",
    "ifHCInMulticastPkts":          "1.3.6.1.2.1.31.1.1.1.8",
    "ifHCInBroadcastPkts":          "1.3.6.1.2.1.31.1.1.1.9",
    "ifHCOutOctets":                "1.3.6.1.2.1.31.1.1.1.10",
    "ifHCOutUcastPkts":             "1.3.6.1.2.1.31.1.1.1.11",
    "ifHCOutMulticastPkts":         "1.3.6.1.2.1.31.1.1.1.12",
    "ifHCOutBroadcastPkts":         "1.3.6.1.2.1.31.1.1.1.13",
    "ifHighSpeed":                  "1.3.6.1.2.1.31.1.1.1.15",
    "ifAlias":                      "1.3.6.1.2.1.31.1.1.1.18",

    # ENTITY-MIB (RFC 4133)
    "entPhysicalTable":             "1.3.6.1.2.1.47.1.1.1.1",
    "entPhysicalDescr":             "1.3.6.1.2.1.47.1.1.1.1.2",
    "entPhysicalVendorType":        "1.3.6.1.2.1.47.1.1.1.1.3",
    "entPhysicalContainedIn":       "1.3.6.1.2.1.47.1.1.1.1.4",
    "entPhysicalClass":             "1.3.6.1.2.1.47.1.1.1.1.5",
    "entPhysicalParentRelPos":      "1.3.6.1.2.1.47.1.1.1.1.6",
    "entPhysicalName":              "1.3.6.1.2.1.47.1.1.1.1.7",
    "entPhysicalHardwareRev":       "1.3.6.1.2.1.47.1.1.1.1.8",
    "entPhysicalFirmwareRev":       "1.3.6.1.2.1.47.1.1.1.1.9",
    "entPhysicalSoftwareRev":       "1.3.6.1.2.1.47.1.1.1.1.10",
    "entPhysicalSerialNum":         "1.3.6.1.2.1.47.1.1.1.1.11",
    "entPhysicalMfgName":           "1.3.6.1.2.1.47.1.1.1.1.12",
    "entPhysicalModelName":         "1.3.6.1.2.1.47.1.1.1.1.13",
    "entPhysicalIsFRU":             "1.3.6.1.2.1.47.1.1.1.1.16",

    # ENTITY-SENSOR-MIB (RFC 3433)
    "entPhySensorTable":            "1.3.6.1.2.1.99.1.1.1",
    "entPhySensorType":             "1.3.6.1.2.1.99.1.1.1.1",
    "entPhySensorScale":            "1.3.6.1.2.1.99.1.1.1.2",
    "entPhySensorPrecision":        "1.3.6.1.2.1.99.1.1.1.3",
    "entPhySensorValue":            "1.3.6.1.2.1.99.1.1.1.4",
    "entPhySensorOperStatus":       "1.3.6.1.2.1.99.1.1.1.5",
    "entPhySensorUnitsDisplay":     "1.3.6.1.2.1.99.1.1.1.6",

    # LLDP-MIB (IEEE 802.1AB)
    "lldpRemTable":                 "1.0.8802.1.1.2.1.4.1.1",
    "lldpRemChassisIdSubtype":      "1.0.8802.1.1.2.1.4.1.1.4",
    "lldpRemChassisId":             "1.0.8802.1.1.2.1.4.1.1.5",
    "lldpRemPortIdSubtype":         "1.0.8802.1.1.2.1.4.1.1.6",
    "lldpRemPortId":                "1.0.8802.1.1.2.1.4.1.1.7",
    "lldpRemPortDesc":              "1.0.8802.1.1.2.1.4.1.1.8",
    "lldpRemSysName":               "1.0.8802.1.1.2.1.4.1.1.9",
    "lldpRemSysDesc":               "1.0.8802.1.1.2.1.4.1.1.10",
    "lldpRemSysCapSupported":       "1.0.8802.1.1.2.1.4.1.1.11",
    "lldpRemSysCapEnabled":         "1.0.8802.1.1.2.1.4.1.1.12",
    "lldpRemManAddrTable":          "1.0.8802.1.1.2.1.4.2.1",
    "lldpLocPortTable":             "1.0.8802.1.1.2.1.3.7.1",
    "lldpLocPortDesc":              "1.0.8802.1.1.2.1.3.7.1.3",

    # BRIDGE-MIB (RFC 4188)
    "dot1dTpFdbTable":              "1.3.6.1.2.1.17.4.3.1",
    "dot1dTpFdbPort":               "1.3.6.1.2.1.17.4.3.1.2",
    "dot1dTpFdbStatus":             "1.3.6.1.2.1.17.4.3.1.3",
    "dot1dBasePortIfIndex":         "1.3.6.1.2.1.17.1.4.1.2",

    # Q-BRIDGE-MIB (RFC 4363)
    "dot1qVlanStaticTable":         "1.3.6.1.2.1.17.7.1.4.3.1",
    "dot1qVlanStaticName":          "1.3.6.1.2.1.17.7.1.4.3.1.1",
    "dot1qVlanStaticEgressPorts":   "1.3.6.1.2.1.17.7.1.4.3.1.2",
    "dot1qVlanStaticUntaggedPorts": "1.3.6.1.2.1.17.7.1.4.3.1.4",
    "dot1qVlanStaticRowStatus":     "1.3.6.1.2.1.17.7.1.4.3.1.5",
    "dot1qVlanCurrentTable":        "1.3.6.1.2.1.17.7.1.4.2.1",
    "dot1qCurrentEgressPorts":      "1.3.6.1.2.1.17.7.1.4.2.1.4",
    "dot1qCurrentUntaggedPorts":    "1.3.6.1.2.1.17.7.1.4.2.1.5",
    "dot1qTpFdbTable":              "1.3.6.1.2.1.17.7.1.2.2.1",
    "dot1qTpFdbPort":               "1.3.6.1.2.1.17.7.1.2.2.1.2",
    "dot1qTpFdbStatus":             "1.3.6.1.2.1.17.7.1.2.2.1.3",

    # IP-FORWARD-MIB (RFC 4292)
    "ipForwardTable":               "1.3.6.1.2.1.4.21.1",
    "ipForwardDest":                "1.3.6.1.2.1.4.21.1.1",
    "ipForwardMetric1":             "1.3.6.1.2.1.4.21.1.3",
    "ipForwardNextHop":             "1.3.6.1.2.1.4.21.1.4",
    "ipForwardIfIndex":             "1.3.6.1.2.1.4.21.1.5",
    "ipForwardType":                "1.3.6.1.2.1.4.21.1.6",
    "ipForwardProto":               "1.3.6.1.2.1.4.21.1.7",
    "ipForwardMask":                "1.3.6.1.2.1.4.21.1.11",

    # IP-MIB (RFC 4293) — ARP
    "ipNetToMediaTable":            "1.3.6.1.2.1.4.22.1",
    "ipNetToMediaIfIndex":          "1.3.6.1.2.1.4.22.1.1",
    "ipNetToMediaPhysAddress":      "1.3.6.1.2.1.4.22.1.2",
    "ipNetToMediaNetAddress":       "1.3.6.1.2.1.4.22.1.3",
    "ipNetToMediaType":             "1.3.6.1.2.1.4.22.1.4",
}

# ---------------------------------------------------------------------------
# Vendor OID Catalog
# ---------------------------------------------------------------------------
# Structure:  vendor_key → domain → metric → OID
#
# vendor_key must match VendorDetector.detect() return values exactly.
# Domains: cpu | memory | system | environment | firewall | wireless
#
# Rules:
#   - Standard MIBs are NOT repeated here — they live in STANDARD_OIDS.
#   - Only OIDs that are NOT in standard MIBs go here.
#   - All OIDs are probed live against the device walk; unused ones are
#     simply absent from the walk result and ignored.
# ---------------------------------------------------------------------------

VENDOR_OID_CATALOG: dict[str, dict[str, dict[str, str]]] = {

    # ------------------------------------------------------------------
    # Cisco Systems  (enterprise 9)
    # ------------------------------------------------------------------
    "cisco": {
        "cpu": {
            # CISCO-PROCESS-MIB cpmCPUTotalTable
            "cpm_5sec":          "1.3.6.1.4.1.9.9.109.1.1.1.1.3",
            "cpm_1min":          "1.3.6.1.4.1.9.9.109.1.1.1.1.6",
            "cpm_5min":          "1.3.6.1.4.1.9.9.109.1.1.1.1.8",
            # Cisco NX-OS
            "nexus_cpu":         "1.3.6.1.4.1.9.9.305.1.1.1.0",
        },
        "memory": {
            # CISCO-MEMORY-POOL-MIB
            "pool_used":         "1.3.6.1.4.1.9.9.48.1.1.1.6",
            "pool_free":         "1.3.6.1.4.1.9.9.48.1.1.1.7",
            "pool_total":        "1.3.6.1.4.1.9.9.48.1.1.1.5",
        },
        "system": {
            "serial":            "1.3.6.1.4.1.9.3.6.3.0",
            "ios_version":       "1.3.6.1.4.1.9.9.25.1.1.1.2.16",
            "model":             "1.3.6.1.4.1.9.9.25.1.1.1.2.11",
        },
        "environment": {
            # CISCO-ENVMON-MIB
            "temp_table":        "1.3.6.1.4.1.9.9.13.1.3.1",
            "temp_descr":        "1.3.6.1.4.1.9.9.13.1.3.1.2",
            "temp_value":        "1.3.6.1.4.1.9.9.13.1.3.1.3",
            "temp_status":       "1.3.6.1.4.1.9.9.13.1.3.1.6",
            "fan_table":         "1.3.6.1.4.1.9.9.13.1.4.1",
            "fan_descr":         "1.3.6.1.4.1.9.9.13.1.4.1.2",
            "fan_status":        "1.3.6.1.4.1.9.9.13.1.4.1.3",
            "psu_table":         "1.3.6.1.4.1.9.9.13.1.5.1",
            "psu_descr":         "1.3.6.1.4.1.9.9.13.1.5.1.2",
            "psu_status":        "1.3.6.1.4.1.9.9.13.1.5.1.3",
        },
        "firewall": {
            # CISCO-FIREWALL-MIB (ASA)
            "conn_count":        "1.3.6.1.4.1.9.9.147.1.2.2.2.1.5.40.6",
            "conn_limit":        "1.3.6.1.4.1.9.9.147.1.2.2.2.1.5.40.7",
            # CISCO-REMOTE-ACCESS-MONITOR-MIB
            "vpn_users":         "1.3.6.1.4.1.9.9.392.1.3.29.0",
        },
        "cdp": {
            "cache_table":       "1.3.6.1.4.1.9.9.23.1.2.1.1",
            "device_id":         "1.3.6.1.4.1.9.9.23.1.2.1.1.6",
            "device_port":       "1.3.6.1.4.1.9.9.23.1.2.1.1.7",
            "platform":          "1.3.6.1.4.1.9.9.23.1.2.1.1.8",
            "capabilities":      "1.3.6.1.4.1.9.9.23.1.2.1.1.9",
            "version":           "1.3.6.1.4.1.9.9.23.1.2.1.1.10",
            "duplex":            "1.3.6.1.4.1.9.9.23.1.2.1.1.11",
            "addr_table":        "1.3.6.1.4.1.9.9.23.1.2.2.1.4",
        },
        "wireless": {
            "ap_count":          "1.3.6.1.4.1.9.9.619.1.1.1.0",
            "client_count":      "1.3.6.1.4.1.9.9.619.1.2.1.0",
            "ssid_table":        "1.3.6.1.4.1.9.9.512.1.1.1.1",
        },
    },

    # ------------------------------------------------------------------
    # Fortinet  (enterprise 12356)
    # ------------------------------------------------------------------
    "fortinet": {
        "cpu": {
            "overall":           "1.3.6.1.4.1.12356.101.4.1.3.0",
            "kernel":            "1.3.6.1.4.1.12356.101.4.1.8.0",
            "idle":              "1.3.6.1.4.1.12356.101.4.1.5.0",
        },
        "memory": {
            "total_real":        "1.3.6.1.4.1.12356.101.4.5.1.0",
            "used_real":         "1.3.6.1.4.1.12356.101.4.5.2.0",
        },
        "system": {
            "serial":            "1.3.6.1.4.1.12356.100.1.1.1.0",
            "model":             "1.3.6.1.4.1.12356.100.1.1.2.0",
            "firmware":          "1.3.6.1.4.1.12356.100.1.1.3.0",
            "ha_mode":           "1.3.6.1.4.1.12356.101.13.1.1.0",
        },
        "environment": {
            "sensor_table":      "1.3.6.1.4.1.12356.101.4.3.2.1",
            "sensor_name":       "1.3.6.1.4.1.12356.101.4.3.2.1.2",
            "sensor_value":      "1.3.6.1.4.1.12356.101.4.3.2.1.4",
            "sensor_alarm":      "1.3.6.1.4.1.12356.101.4.3.2.1.6",
        },
        "firewall": {
            "sessions":          "1.3.6.1.4.1.12356.101.4.1.8.0",
            "session_max":       "1.3.6.1.4.1.12356.101.4.1.9.0",
            "vpn_users":         "1.3.6.1.4.1.12356.101.12.2.3.1.1.0",
            "ips_events":        "1.3.6.1.4.1.12356.101.9.1.1.0",
            "threat_count":      "1.3.6.1.4.1.12356.101.9.1.2.0",
            "ha_state":          "1.3.6.1.4.1.12356.101.13.1.3.0",
        },
    },

    # ------------------------------------------------------------------
    # Huawei  (enterprise 2011)
    # ------------------------------------------------------------------
    "huawei": {
        "cpu": {
            "cpu_5s":            "1.3.6.1.4.1.2011.5.25.31.1.1.1.1.5",
            "cpu_1min":          "1.3.6.1.4.1.2011.5.25.31.1.1.1.1.6",
            "cpu_5min":          "1.3.6.1.4.1.2011.5.25.31.1.1.1.1.7",
            "cpu_table":         "1.3.6.1.4.1.2011.5.25.31.1.1.1.1",
        },
        "memory": {
            "total_kb":          "1.3.6.1.4.1.2011.5.25.31.1.1.1.1.8",
            "used_kb":           "1.3.6.1.4.1.2011.5.25.31.1.1.1.1.9",
            "free_kb":           "1.3.6.1.4.1.2011.5.25.31.1.1.1.1.10",
        },
        "system": {
            "serial":            "1.3.6.1.4.1.2011.6.3.9.0",
            "model":             "1.3.6.1.4.1.2011.6.3.3.0",
            "firmware":          "1.3.6.1.4.1.2011.6.3.1.0",
        },
        "environment": {
            "temp_table":        "1.3.6.1.4.1.2011.5.25.31.1.1.10.1",
            "temp_value":        "1.3.6.1.4.1.2011.5.25.31.1.1.10.1.3",
            "fan_table":         "1.3.6.1.4.1.2011.5.25.31.1.1.7.1",
            "fan_status":        "1.3.6.1.4.1.2011.5.25.31.1.1.7.1.7",
            "psu_table":         "1.3.6.1.4.1.2011.5.25.31.1.1.8.1",
            "psu_status":        "1.3.6.1.4.1.2011.5.25.31.1.1.8.1.7",
        },
    },

    # ------------------------------------------------------------------
    # Juniper Networks  (enterprise 2636)
    # ------------------------------------------------------------------
    "juniper": {
        "cpu": {
            "re_cpu_1min":       "1.3.6.1.4.1.2636.3.1.13.1.8",
            "re_cpu_5min":       "1.3.6.1.4.1.2636.3.1.13.1.9",
            "re_cpu_15min":      "1.3.6.1.4.1.2636.3.1.13.1.10",
            "re_table":          "1.3.6.1.4.1.2636.3.1.13.1",
        },
        "memory": {
            "total_bytes":       "1.3.6.1.4.1.2636.3.1.13.1.11",
            "used_bytes":        "1.3.6.1.4.1.2636.3.1.13.1.12",
        },
        "system": {
            "serial":            "1.3.6.1.4.1.2636.3.1.3.0",
            "model":             "1.3.6.1.4.1.2636.3.1.2.0",
            "os_version":        "1.3.6.1.4.1.2636.3.1.5.0",
        },
        "environment": {
            "fan_table":         "1.3.6.1.4.1.2636.3.1.14.1",
            "fan_status":        "1.3.6.1.4.1.2636.3.1.14.1.5",
            "psu_table":         "1.3.6.1.4.1.2636.3.1.15.1",
            "psu_status":        "1.3.6.1.4.1.2636.3.1.15.1.6",
        },
    },

    # ------------------------------------------------------------------
    # Palo Alto Networks  (enterprise 25461)
    # ------------------------------------------------------------------
    "paloalto": {
        "cpu": {
            "mgmt_cpu":          "1.3.6.1.4.1.25461.2.1.2.1.3.0",
            "data_cpu":          "1.3.6.1.4.1.25461.2.1.2.1.4.0",
            "dp_table":          "1.3.6.1.4.1.25461.2.1.2.3.5.1",
        },
        "memory": {
            "total_kb":          "1.3.6.1.4.1.25461.2.1.2.1.5.0",
            "used_kb":           "1.3.6.1.4.1.25461.2.1.2.1.6.0",
        },
        "system": {
            "serial":            "1.3.6.1.4.1.25461.2.1.2.1.1.0",
            "model":             "1.3.6.1.4.1.25461.2.1.2.1.2.0",
            "sw_version":        "1.3.6.1.4.1.25461.2.1.2.1.10.0",
            "ha_local_state":    "1.3.6.1.4.1.25461.2.1.2.1.11.0",
        },
        "firewall": {
            "active_sessions":   "1.3.6.1.4.1.25461.2.1.2.4.3.0",
            "max_sessions":      "1.3.6.1.4.1.25461.2.1.2.4.6.0",
            "active_tcp":        "1.3.6.1.4.1.25461.2.1.2.4.4.0",
            "active_udp":        "1.3.6.1.4.1.25461.2.1.2.4.5.0",
            "threat_count":      "1.3.6.1.4.1.25461.2.1.3.4.0",
            "ips_events":        "1.3.6.1.4.1.25461.2.1.3.5.0",
            "vpn_tunnels":       "1.3.6.1.4.1.25461.2.1.2.5.1.0",
            "ha_local_state":    "1.3.6.1.4.1.25461.2.1.2.1.11.0",
            "ha_peer_state":     "1.3.6.1.4.1.25461.2.1.2.1.12.0",
        },
    },

    # ------------------------------------------------------------------
    # MikroTik / RouterOS  (enterprise 14988)
    # ------------------------------------------------------------------
    "mikrotik": {
        "cpu": {
            "cpu_load":          "1.3.6.1.2.1.25.3.3.1.2.1",
        },
        "memory": {
            "total_kb":          "1.3.6.1.4.1.14988.1.1.1.2.0",
            "free_kb":           "1.3.6.1.4.1.14988.1.1.1.3.0",
        },
        "system": {
            "firmware":          "1.3.6.1.4.1.14988.1.1.4.4.0",
            "serial":            "1.3.6.1.4.1.14988.1.1.7.3.0",
            "board_name":        "1.3.6.1.4.1.14988.1.1.7.8.0",
        },
        "environment": {
            "temp_value":        "1.3.6.1.4.1.14988.1.1.3.10.0",
            "voltage":           "1.3.6.1.4.1.14988.1.1.3.8.0",
            "current":           "1.3.6.1.4.1.14988.1.1.3.9.0",
        },
        "wireless": {
            "ssid":              "1.3.6.1.4.1.14988.1.1.1.3.1.4",
            "client_count":      "1.3.6.1.4.1.14988.1.1.1.3.1.6",
            "channel":           "1.3.6.1.4.1.14988.1.1.1.3.1.5",
            "signal_table":      "1.3.6.1.4.1.14988.1.1.1.2.1.3",
            "noise_table":       "1.3.6.1.4.1.14988.1.1.1.2.1.17",
        },
    },

    # ------------------------------------------------------------------
    # Sophos UTM / XG  (enterprise 2604 / 21067)
    # ------------------------------------------------------------------
    "sophos": {
        "cpu": {
            "overall":           "1.3.6.1.4.1.2604.5.1.2.1.0",
            "user":              "1.3.6.1.4.1.2604.5.1.2.2.0",
            "sys":               "1.3.6.1.4.1.2604.5.1.2.3.0",
            "idle":              "1.3.6.1.4.1.2604.5.1.2.4.0",
        },
        "memory": {
            "total_kb":          "1.3.6.1.4.1.2604.5.1.3.1.0",
            "free_kb":           "1.3.6.1.4.1.2604.5.1.3.2.0",
            "used_kb":           "1.3.6.1.4.1.2604.5.1.3.3.0",
        },
        "system": {
            "firmware":          "1.3.6.1.4.1.2604.5.1.1.1.0",
            "model":             "1.3.6.1.4.1.2604.5.1.1.2.0",
        },
        "firewall": {
            "conn_current":      "1.3.6.1.4.1.2604.5.1.5.1.0",
            "conn_max":          "1.3.6.1.4.1.2604.5.1.5.2.0",
            "live_users":        "1.3.6.1.4.1.2604.5.1.6.1.0",
            "ips_events":        "1.3.6.1.4.1.2604.5.1.7.1.0",
            "ha_status":         "1.3.6.1.4.1.2604.5.1.1.3.0",
        },
    },

    # ------------------------------------------------------------------
    # Linux / net-snmp  (enterprise 8072) — UCD-SNMP is in STANDARD_OIDS
    # ------------------------------------------------------------------
    "linux": {
        "system": {
            "os_version":        "1.3.6.1.4.1.2021.100.4.0",
        },
    },

    # ------------------------------------------------------------------
    # Microsoft Windows  (enterprise 311)
    # ------------------------------------------------------------------
    "windows": {
        "system": {
            "os_version":        "1.3.6.1.4.1.311.1.1.3.1.1.0",
        },
        # CPU and memory are via HR-MIB (STANDARD_OIDS)
    },

    # ------------------------------------------------------------------
    # VMware ESXi  (enterprise 6876)
    # ------------------------------------------------------------------
    "vmware": {
        "system": {
            "product_name":      "1.3.6.1.4.1.6876.1.1.0",
            "version":           "1.3.6.1.4.1.6876.1.2.0",
            "build_number":      "1.3.6.1.4.1.6876.1.4.0",
        },
        "cpu": {
            "num_cpus":          "1.3.6.1.4.1.6876.2.4.1.4.0",
            "cpu_speed_mhz":     "1.3.6.1.4.1.6876.2.4.1.6.0",
        },
        "memory": {
            "total_mb":          "1.3.6.1.4.1.6876.2.4.1.5.0",
        },
    },

    # ------------------------------------------------------------------
    # Arista EOS  (enterprise 30065)
    # ------------------------------------------------------------------
    "arista": {
        "cpu": {
            "overall":           "1.3.6.1.2.1.25.3.3.1.2.1",
        },
        "system": {
            "serial":            "1.3.6.1.2.1.47.1.1.1.1.11.1",
            "model":             "1.3.6.1.2.1.47.1.1.1.1.13.1",
        },
    },

    # ------------------------------------------------------------------
    # HP / HPE ProCurve / Comware  (enterprise 11)
    # ------------------------------------------------------------------
    "hp": {
        "cpu": {
            "overall":           "1.3.6.1.4.1.11.2.14.11.5.1.9.6.1.0",
        },
        "memory": {
            "total_kb":          "1.3.6.1.4.1.11.2.14.11.5.1.1.2.1.1.1.5.1",
            "free_kb":           "1.3.6.1.4.1.11.2.14.11.5.1.1.2.1.1.1.6.1",
        },
    },

    # ------------------------------------------------------------------
    # Aruba Networks  (enterprise 14823)
    # ------------------------------------------------------------------
    "aruba": {
        "wireless": {
            "ap_count":          "1.3.6.1.4.1.14823.2.2.1.1.3.1.0",
            "client_count":      "1.3.6.1.4.1.14823.2.2.1.1.3.2.0",
            "ssid_table":        "1.3.6.1.4.1.14823.2.2.1.1.7.1.1",
        },
    },

    # ------------------------------------------------------------------
    # Ubiquiti UniFi  (enterprise 41112)
    # ------------------------------------------------------------------
    "ubiquiti": {
        "wireless": {
            "ap_count":          "1.3.6.1.4.1.41112.1.6.1.1.0",
            "ssid":              "1.3.6.1.4.1.41112.1.6.1.2.1.4",
            "client_count":      "1.3.6.1.4.1.41112.1.6.1.2.1.6",
        },
    },

    # ------------------------------------------------------------------
    # F5 BIG-IP  (enterprise 3375)
    # ------------------------------------------------------------------
    "f5": {
        "cpu": {
            "overall":           "1.3.6.1.4.1.3375.2.1.1.2.1.45.0",
        },
        "memory": {
            "total_kb":          "1.3.6.1.4.1.3375.2.1.1.2.1.143.0",
            "used_kb":           "1.3.6.1.4.1.3375.2.1.1.2.1.144.0",
        },
        "firewall": {
            "connections":       "1.3.6.1.4.1.3375.2.1.1.2.1.23.0",
        },
    },

    # ------------------------------------------------------------------
    # Check Point  (enterprise 2620)
    # ------------------------------------------------------------------
    "checkpoint": {
        "cpu": {
            "overall":           "1.3.6.1.4.1.2620.1.6.7.2.4.0",
        },
        "memory": {
            "total_kb":          "1.3.6.1.4.1.2620.1.6.7.4.3.0",
            "used_kb":           "1.3.6.1.4.1.2620.1.6.7.4.4.0",
        },
        "firewall": {
            "connections":       "1.3.6.1.4.1.2620.1.1.25.3.0",
            "ha_status":         "1.3.6.1.4.1.2620.1.5.100.0",
        },
    },
}

# ---------------------------------------------------------------------------
# sysObjectID prefix → vendor_key  (longest-prefix wins at runtime)
# ---------------------------------------------------------------------------
VENDOR_SYSOID_PREFIXES: dict[str, str] = {
    "1.3.6.1.4.1.9.":        "cisco",
    "1.3.6.1.4.1.12356.":    "fortinet",
    "1.3.6.1.4.1.2011.":     "huawei",
    "1.3.6.1.4.1.2636.":     "juniper",
    "1.3.6.1.4.1.25461.":    "paloalto",
    "1.3.6.1.4.1.14988.":    "mikrotik",
    "1.3.6.1.4.1.6876.":     "vmware",
    "1.3.6.1.4.1.2604.":     "sophos",
    "1.3.6.1.4.1.21067.":    "sophos",
    "1.3.6.1.4.1.311.":      "windows",
    "1.3.6.1.4.1.8072.":     "linux",
    "1.3.6.1.4.1.30065.":    "arista",
    "1.3.6.1.4.1.11.":       "hp",
    "1.3.6.1.4.1.14823.":    "aruba",
    "1.3.6.1.4.1.41112.":    "ubiquiti",
    "1.3.6.1.4.1.6574.":     "synology",
    "1.3.6.1.4.1.24681.":    "qnap",
    "1.3.6.1.4.1.1916.":     "extreme",
    "1.3.6.1.4.1.1588.":     "brocade",
    "1.3.6.1.4.1.3375.":     "f5",
    "1.3.6.1.4.1.2620.":     "checkpoint",
    "1.3.6.1.4.1.674.":      "dell",
    "1.3.6.1.4.1.30155.":    "openbsd",
}

# ---------------------------------------------------------------------------
# sysDescr keyword → vendor_key
# (case-insensitive substring match; order determines priority on ties)
# ---------------------------------------------------------------------------
VENDOR_DESCR_KEYWORDS: dict[str, list[str]] = {
    "cisco":      ["cisco ios", "cisco nx-os", "catalyst", "nexus", "cisco asa", "ftd", "asr", "isr"],
    "fortinet":   ["fortigate", "fortios", "fortiswitch", "fortiap", "fortinet"],
    "huawei":     ["huawei", "vrp", "quidway"],
    "juniper":    ["juniper", "junos"],
    "paloalto":   ["pan-os", "palo alto", "pa-"],
    "mikrotik":   ["mikrotik", "routeros", "routerboard"],
    "vmware":     ["vmware esxi", "esxi", "vsphere"],
    "sophos":     ["sophos", "utm", "cyberoam"],
    "windows":    ["windows server", "windows nt", "microsoft windows"],
    "linux":      ["linux", "ubuntu", "debian", "centos", "rhel", "fedora", "suse", "alpine", "net-snmp", "ucd-snmp"],
    "arista":     ["arista eos"],
    "hp":         ["hp procurve", "hp comware", "hewlett-packard", "hpe"],
    "aruba":      ["aruba os", "aruba networks", "aruba instant"],
    "ubiquiti":   ["ubiquiti", "airmax", "unifi", "edgeos"],
    "f5":         ["bigip", "f5 networks", "tmos"],
    "checkpoint": ["check point", "gaia os"],
    "extreme":    ["extremexos", "exos", "extreme networks"],
    "brocade":    ["brocade", "fabricos"],
}

# ---------------------------------------------------------------------------
# Decode tables — shared across collectors
# ---------------------------------------------------------------------------

# ENTITY-MIB entPhysicalClass
ENTITY_PHYSICAL_CLASS: dict[int, str] = {
    1: "other", 2: "unknown", 3: "chassis", 4: "backplane",
    5: "container", 6: "powerSupply", 7: "fan", 8: "sensor",
    9: "module", 10: "port", 11: "stack", 12: "cpu",
}

# ENTITY-SENSOR-MIB entPhySensorType  →  (type_label, default_unit)
ENTITY_SENSOR_TYPE: dict[str, tuple[str, str]] = {
    "1":  ("other",        ""),     "2":  ("unknown",   ""),
    "3":  ("voltage",      "V AC"), "4":  ("voltage",   "V DC"),
    "5":  ("current",      "A"),    "6":  ("power",     "W"),
    "7":  ("frequency",    "Hz"),   "8":  ("temperature","°C"),
    "9":  ("humidity",     "%RH"),  "10": ("fan",       "RPM"),
    "11": ("flow",         "cmm"),  "12": ("state",     "bool"),
}

# ENTITY-SENSOR-MIB entPhySensorScale  →  multiplier
ENTITY_SENSOR_SCALE: dict[str, float] = {
    "1": 1e-24, "2": 1e-21, "3": 1e-18, "4": 1e-15, "5": 1e-12,
    "6": 1e-9,  "7": 1e-6,  "8": 1e-3,  "9": 1.0,   "10": 1e3,
    "11": 1e6,  "12": 1e9,  "13": 1e12, "14": 1e15, "15": 1e18,
}

# hrStorageType OID suffix → label
HR_STORAGE_TYPES: dict[str, str] = {
    "1.3.6.1.2.1.25.2.1.1":  "other",
    "1.3.6.1.2.1.25.2.1.2":  "ram",
    "1.3.6.1.2.1.25.2.1.3":  "virtualMemory",
    "1.3.6.1.2.1.25.2.1.4":  "fixedDisk",
    "1.3.6.1.2.1.25.2.1.5":  "removableDisk",
    "1.3.6.1.2.1.25.2.1.9":  "flashMemory",
    "1.3.6.1.2.1.25.2.1.10": "networkDisk",
}

# ipForwardProto codes
ROUTING_PROTOCOLS: dict[str, str] = {
    "1": "other",  "2": "local",   "3": "netmgmt", "4": "icmp",
    "5": "egp",    "6": "ggp",     "7": "hello",   "8": "rip",
    "9": "is-is",  "13": "ospf",   "14": "bgp",    "16": "ciscoEigrp",
}

# ifAdminStatus / ifOperStatus
IF_ADMIN_STATUS: dict[str, str] = {"1": "up", "2": "down", "3": "testing"}
IF_OPER_STATUS:  dict[str, str] = {
    "1": "up", "2": "down", "3": "testing",
    "4": "unknown", "5": "dormant", "6": "notPresent", "7": "lowerLayerDown",
}

# Vendor-specific HA / sensor status decode maps — keyed by vendor + field
VENDOR_STATUS_MAPS: dict[str, dict[str, dict[str, str]]] = {
    "cisco": {
        "env_status": {
            "1": "normal", "2": "warning", "3": "critical",
            "4": "shutdown", "5": "notPresent", "6": "notFunctioning",
        },
    },
    "fortinet": {
        "ha_state":     {"1": "standalone", "2": "active", "3": "passive", "4": "electing"},
        "sensor_alarm": {"0": "ok", "1": "alarm"},
    },
    "juniper": {
        "fan_status":   {"1": "unknown", "2": "ok", "3": "absent", "4": "failed"},
        "psu_status":   {
            "1": "unknown", "2": "empty", "3": "present", "4": "ready",
            "6": "online",  "8": "offline", "9": "off", "10": "ac_failed",
            "11": "dc_failed", "12": "temp_failed",
        },
    },
    "huawei": {
        "fan_status":   {"1": "normal", "2": "abnormal"},
        "psu_status":   {"1": "normal", "2": "abnormal", "3": "notPresent"},
    },
    "paloalto": {
        "ha_local_state": {
            "0": "disabled", "1": "passive", "2": "active",
            "3": "active_primary", "4": "active_secondary",
        },
    },
    "sophos": {
        "ha_status": {"0": "standalone", "1": "primary", "2": "auxiliary", "3": "faulty"},
    },
}


def get_vendor_oid(vendor: str, domain: str, metric: str) -> str | None:
    """
    Look up a vendor-specific OID from the catalog.
    Returns None if the vendor/domain/metric combination is not catalogued.
    This is the ONLY function collectors should call for vendor OIDs.
    """
    return VENDOR_OID_CATALOG.get(vendor, {}).get(domain, {}).get(metric)


def get_standard_oid(key: str) -> str | None:
    """Look up a standard MIB OID by its mnemonic key."""
    return STANDARD_OIDS.get(key)


def get_all_vendor_oids_for_domain(vendor: str, domain: str) -> dict[str, str]:
    """Return all metric→OID pairs for a given vendor+domain."""
    return dict(VENDOR_OID_CATALOG.get(vendor, {}).get(domain, {}))


def decode_vendor_status(vendor: str, field: str, code: int | str) -> str:
    """Translate a numeric status code to a human label using VENDOR_STATUS_MAPS."""
    mapping = VENDOR_STATUS_MAPS.get(vendor, {}).get(field, {})
    return mapping.get(str(code), str(code))
