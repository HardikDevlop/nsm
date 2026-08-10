# SNMP Device Discovery Bugs - Bugfix Requirements

## Introduction

The NMS device discovery system has three interconnected bugs affecting SNMP and mixed-protocol discovery workflows:

1. **SNMP Discovery Not Detecting Devices**: When users run SNMP discovery on a subnet with valid SNMPv3 credentials, the system returns "No SNMP response received before timeout" even when devices have SNMP enabled.

2. **Device Conflicts When Mixing Protocols**: When users discover devices via ICMP first (which works), then run SNMP discovery, the previously ICMP-discovered devices are deleted from the database instead of being merged.

3. **Frontend SNMPv3 Form Issues**: The SNMPv3 discovery form requests "Enter an IP address" even when only using SNMPv3 authentication passwords, and doesn't dynamically hide/show fields based on selected SNMP version.

These bugs prevent users from building comprehensive device inventories using multiple discovery protocols and result in data loss during discovery operations.

---

## Bug Analysis

### Current Behavior (Defect)

#### Bug 1: SNMP Discovery Timeout Failures

1.1 WHEN a user runs SNMP discovery on a subnet (e.g., 192.168.100.0/24) with SNMPv3 credentials (username, auth_protocol, auth_password, privacy_protocol, privacy_password, security_level), THEN the system returns "No SNMP response received before timeout" error even though at least one device on the subnet has SNMP enabled and is reachable

1.2 WHEN SNMPDiscovery.collect() is called with SNMPv3 parameters where privacy_protocol is None or auth_protocol is missing, THEN the SNMPClient fails to construct valid UsmUserData credentials and times out without properly formatting the security parameters

1.3 WHEN SNMPClient._auth() receives SNMPv3 credentials with None values for auth_protocol or privacy_protocol, THEN the pysnmp UsmUserData constructor receives None/invalid parameters instead of omitting optional fields, causing SNMP negotiation to fail

#### Bug 2: ICMP Devices Deleted During SNMP Discovery

2.1 WHEN a user discovers devices via ICMP protocol first (e.g., 10 devices detected), then runs SNMP discovery on the same subnet, THEN previously ICMP-discovered devices are deleted from the database instead of being merged with SNMP results

2.2 WHEN the database contains Device records created by ICMP discovery with status="online" and monitoring_status=True, and the user then runs SNMP discovery that finds no SNMP-enabled devices on that subnet, THEN the SNMP discovery endpoint throws an HTTPException with status 502, but some ICMP devices get marked as deleted (deleted_at is set)

2.3 WHEN add_discovered_devices() is called in the chunked scan callback with an empty or partial device list from SNMP discovery, THEN the database transaction may delete or soft-delete devices that were created by previous discovery methods without properly handling the upsert logic

#### Bug 3: SNMPv3 Frontend Form Not Dynamic

3.1 WHEN a user selects SNMPv3 as the SNMP version in the discovery form, THEN the form still displays "Enter an IP address" field as required, even when the user only wants to provide auth credentials and should discover via subnet scan (subnet field should be the entry point instead)

3.2 WHEN SNMPv3 is selected and the user leaves the IP address field empty but provides auth_password and privacy_password, THEN the frontend form validation rejects the submission because it requires either IP address OR subnet, but SNMPv3 discovery is only implemented for subnet-based discovery

### Expected Behavior (Correct)

#### Bug 1: SNMP Discovery Should Detect Devices

2.1 WHEN a user runs SNMP discovery on a subnet with SNMPv3 credentials where privacy_protocol is None, THEN the SNMPClient SHALL construct valid UsmUserData with only auth_protocol specified, and the SNMP query SHALL successfully retrieve data from SNMPv3 devices that support authentication-only security level

2.2 WHEN SNMPClient._auth() receives SNMPv3 credentials with optional fields (auth_protocol, privacy_protocol) as None, THEN it SHALL properly omit those fields when constructing UsmUserData, using only the non-None security parameters

2.3 WHEN SNMPDiscovery.collect() is called with valid SNMPv3 parameters on a reachable device with SNMP enabled, THEN the system SHALL successfully retrieve system information (sysName, sysDescr, etc.) and interfaces without timeout errors

#### Bug 2: ICMP Devices Should Not Be Deleted During SNMP Discovery

3.1 WHEN SNMP discovery runs on a subnet that previously had ICMP-discovered devices, THEN all ICMP-discovered devices SHALL remain in the database with their existing data unchanged (hostname, ip_address, mac_address, monitoring_status, etc.) - they SHALL NOT be deleted or marked as deleted

3.2 WHEN add_discovered_devices() receives an empty or partial device list from SNMP discovery, THEN the function SHALL treat this as a partial update and ONLY upsert the devices that were actually discovered via SNMP, WITHOUT modifying or deleting any existing devices from other discovery methods

3.3 WHEN the chunked scan callback processes SNMP discovery results that return 0 devices (no SNMP response), THEN the callback SHALL NOT call add_discovered_devices() with an empty list, and the endpoint SHALL return an appropriate error WITHOUT attempting to update the device database

#### Bug 3: SNMPv3 Form Should Be Dynamic

4.1 WHEN a user selects SNMPv3 as the SNMP version in the frontend discovery form, THEN the form SHALL dynamically show subnet-based discovery options and the IP address field SHALL become optional or hidden, allowing the user to proceed with just auth_password and privacy_password

4.2 WHEN the user provides auth_password without privacy_password in SNMPv3 mode, THEN the form SHALL allow submission and pass privacy_protocol=None to the backend (supporting authentication-only security level)

### Unchanged Behavior (Regression Prevention)

5.1 WHEN ICMP discovery runs on a subnet and discovers devices, THEN the system SHALL create Device records with status="online" and monitoring_status=True exactly as it does currently

5.2 WHEN a user runs SNMP discovery on a subnet with SNMPv2c and valid community strings, THEN the system SHALL continue to work exactly as before, detecting devices and merging them with existing records

5.3 WHEN SNMP discovery successfully finds SNMP-enabled devices, THEN the system SHALL create Device records with SNMP credentials stored in DeviceCredential table exactly as it does currently

5.4 WHEN the topology graph loads device data from the database, THEN it SHALL correctly display all non-deleted devices and their connections regardless of which discovery method was used to find them

5.5 WHEN a user clicks "Add device" button in the frontend to manually add a device, THEN the device SHALL remain in the database and not be affected by subsequent discovery operations

---

## Bug Condition Pseudocode (For Reference)

```pascal
// Bug Condition 1: SNMP Discovery Failure
FUNCTION isSNMPv3TimeoutBug(discoveryParams)
  INPUT: discoveryParams containing snmp_version, auth_protocol, privacy_protocol, etc.
  OUTPUT: boolean
  
  RETURN discoveryParams.snmp_version IN ['v3', 'SNMPv3']
         AND (discoveryParams.privacy_protocol IS NULL OR discoveryParams.auth_protocol IS NULL)
         AND SNMPClient._auth() constructs UsmUserData with None parameters
         AND SNMP query times out instead of returning results
END FUNCTION

// Bug Condition 2: Device Deletion During Mixed Discovery
FUNCTION isDeviceDeletionBug(discoveryWorkflow)
  INPUT: discoveryWorkflow with [ICMP discovery results] followed by [SNMP discovery]
  OUTPUT: boolean
  
  RETURN Device records created by ICMP discovery exist in database
         AND SNMP discovery runs on same subnet with 0 SNMP-enabled devices
         AND add_discovered_devices() is called with empty/partial results
         AND Device.deleted_at is set for ICMP-discovered devices
END FUNCTION

// Bug Condition 3: Frontend Form Not Dynamic
FUNCTION isFormNotDynamicBug(formState)
  INPUT: formState with selected SNMP version = SNMPv3
  OUTPUT: boolean
  
  RETURN IP address field is required
         AND form does not show dynamic field management based on SNMPv3 selection
         AND user cannot submit form with subnet but no IP address
END FUNCTION
```

