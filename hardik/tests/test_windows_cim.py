import pytest
import xml.etree.ElementTree as ET
from requests.exceptions import SSLError, Timeout
from pypsrp.exceptions import AuthenticationError, WinRMTransportError, WSManFaultError

from backend.windows_monitoring.cim import CIMError, CIMLimits, USBControllerDeviceResult, USBHubResult, WindowsCIMClient
from tests.windows_cim_fixtures import FakeWSMan, body, make_client, node, response


def test_os_and_cpu_success_are_typed_and_tls_configured():
    fake = FakeWSMan([response(node("Win32_OperatingSystem", {"CSName": "WIN01", "Caption": "Windows", "Version": "10", "TotalVisibleMemorySize": "1024", "FreePhysicalMemory": "512"}))])
    client, captured = make_client(fake, trusted_ca_path="/ca.pem")
    result = client.operating_system()
    assert result[0].hostname == "WIN01" and result[0].total_memory_bytes == 1024 * 1024
    assert captured["ssl"] is True and captured["auth"] == "ntlm" and captured["cert_validation"] == "/ca.pem"

    fake.pages = [response(node("Win32_PerfFormattedData_PerfOS_Processor", {"Name": "_Total", "PercentProcessorTime": "12.5"}))]
    assert client.processor()[0].percent_processor_time == 12.5
    assert fake.closed


def test_cpu_performance_preserves_logical_processors_and_optional_counters():
    processors = node("Win32_PerfFormattedData_PerfOS_Processor", {
        "Name": "_Total", "PercentProcessorTime": "25", "PercentUserTime": "10",
        "PercentPrivilegedTime": "5", "PercentIdleTime": "75", "InterruptsPerSec": "12",
        "ContextSwitchesPerSec": "100",
    }) + node("Win32_PerfFormattedData_PerfOS_Processor", {
        "Name": "0", "PercentProcessorTime": "20", "PercentUserTime": "8",
    }) + node("Win32_PerfFormattedData_PerfOS_Processor", {
        "Name": "1", "PercentProcessorTime": "30", "PercentIdleTime": "70",
    })
    fake = FakeWSMan([response(processors), response(node("Win32_PerfFormattedData_PerfOS_System", {"ProcessorQueueLength": "2"}))])
    client, _ = make_client(fake)

    result = client.processor_performance()
    queue = client.system_performance()

    assert [row.name for row in result] == ["_Total", "0", "1"]
    assert result[1].usage_percent == 20 and result[1].user_percent == 8
    assert result[2].privileged_percent is None
    assert queue[0].processor_queue_length == 2
    assert queue[0].context_switches_per_sec is None


def test_memory_performance_uses_allowlisted_properties_and_normalizes_values():
    fields = {"AvailableMBytes": "1024", "PagesPersec": "2.5", "PageReadsPersec": "1", "PageWritesPersec": "3", "PageFaultsPersec": "4", "CommittedBytes": "1000", "CommitLimit": "2000", "CacheBytes": "500", "PoolPagedBytes": "100", "PoolNonpagedBytes": "50", "PercentCommittedBytesInUse": "50"}
    fake = FakeWSMan([response(node("Win32_PerfFormattedData_PerfOS_Memory", fields))])
    client, _ = make_client(fake)
    result = client.memory_performance()[0]
    query = WindowsCIMClient._filter("Win32_PerfFormattedData_PerfOS_Memory").text
    assert "AvailableMBytes" in query and "PercentCommittedBytesInUse" in query
    assert result.available_mbytes == 1024 and result.pages_per_sec == 2.5
    assert result.committed_bytes == 1000


def test_memory_performance_missing_invalid_and_negative_values_are_none():
    fake = FakeWSMan([response(node("Win32_PerfFormattedData_PerfOS_Memory", {"AvailableMBytes": "bad", "PagesPersec": "-1"}))])
    client, _ = make_client(fake)
    result = client.memory_performance()[0]
    assert result.available_mbytes is None and result.pages_per_sec is None


def test_memory_performance_accepts_case_variants_and_legitimate_zeroes():
    fake = FakeWSMan([response(node("Win32_PerfFormattedData_PerfOS_Memory", {"pagesperSEC": "0", "PAGEREADSPERSEC": "0", "PageWritesPERSEC": "0", "pagefaultsperSEC": "132"}))])
    client, _ = make_client(fake)
    result = client.memory_performance()[0]
    assert result.pages_per_sec == 0
    assert result.page_reads_per_sec == 0
    assert result.page_writes_per_sec == 0
    assert result.page_faults_per_sec == 132


def test_disk_performance_projection_and_normalization_exclude_nothing_at_cim_layer():
    fields = {"Name": "0 C:", "DiskReadsPerSec": "0", "DiskWritesPerSec": "2", "DiskTransfersPerSec": "2", "DiskReadBytesPerSec": "0", "DiskWriteBytesPerSec": "4096", "DiskBytesPerSec": "4096", "AvgDiskSecPerRead": "0.001", "AvgDiskSecPerWrite": "0.002", "AvgDiskSecPerTransfer": "0.0015", "AvgDiskQueueLength": "0", "CurrentDiskQueueLength": "0", "SplitIOPerSec": "0", "PercentDiskTime": "4"}
    fake = FakeWSMan([response(node("Win32_PerfFormattedData_PerfDisk_LogicalDisk", fields))])
    client, _ = make_client(fake)
    result = client.disk_performance("logical")[0]
    query = WindowsCIMClient._filter("Win32_PerfFormattedData_PerfDisk_LogicalDisk").text
    assert all(field in query for field in ("DiskReadsPerSec", "AvgDiskSecPerRead", "SplitIOPerSec"))
    assert result.read_iops == 0 and result.write_iops == 2
    assert result.read_latency_ms == 1 and result.write_latency_ms == 2
    assert result.current_queue_length == 0


def test_disk_performance_preserves_logical_and_physical_instances():
    logical = node("Win32_PerfFormattedData_PerfDisk_LogicalDisk", {"Name": "_Total", "DiskReadsPerSec": "1"}) + node("Win32_PerfFormattedData_PerfDisk_LogicalDisk", {"Name": "0 C:", "DiskReadsPerSec": "2"})
    physical = node("Win32_PerfFormattedData_PerfDisk_PhysicalDisk", {"Name": "0", "DiskReadsPerSec": "3"})
    fake = FakeWSMan([response(logical), response(physical)])
    client, _ = make_client(fake)
    assert [row.instance for row in client.disk_performance("logical")] == ["_Total", "0 C:"]
    assert [row.instance for row in client.disk_performance("physical")] == ["0"]


def test_disk_inventory_maps_multiple_partitions_and_unmapped_partition():
    physical = response(node("Win32_DiskDrive", {"DeviceID": "\\\\.\\PHYSICALDRIVE0", "Index": "0", "Model": "NVMe", "Size": "1000", "Partitions": "2", "BytesPerSector": "512"}))
    partitions = response(node("Win32_DiskPartition", {"DeviceID": "Disk #0, Partition #1", "DiskIndex": "0", "Index": "1", "Size": "500", "StartingOffset": "1048576", "BootPartition": "true", "PrimaryPartition": "true"}) + node("Win32_DiskPartition", {"DeviceID": "Disk #0, Partition #2", "DiskIndex": "0", "Index": "2", "Size": "500"}))
    links = response(node("Win32_LogicalDiskToPartition", {"Antecedent": '\\\\.\\root\\cimv2:Win32_DiskPartition.DeviceID="Disk #0, Partition #1"', "Dependent": '\\\\.\\root\\cimv2:Win32_LogicalDisk.DeviceID="C:"'}))
    modern = response(node("MSFT_PhysicalDisk", {"FriendlyName": "NVMe", "MediaType": "4", "BusType": "17", "HealthStatus": "Healthy"}))
    fake = FakeWSMan([physical, partitions, links, modern])
    client, _ = make_client(fake)
    result = client.disk_inventory()
    assert result["physical_disks"][0]["size_bytes"] == 1000
    assert result["partitions"][0]["logical_volumes"] == ["C:"]
    assert result["partitions"][1]["logical_volumes"] == []
    assert result["modern_physical_disks"][0]["FriendlyName"] == "NVMe"


def test_disk_inventory_optional_storage_namespace_failure_does_not_break_win32_inventory():
    physical = response(node("Win32_DiskDrive", {"DeviceID": "\\\\.\\PHYSICALDRIVE0", "Index": "0"}))
    partitions = response(node("Win32_DiskPartition", {"DeviceID": "Disk #0, Partition #1", "DiskIndex": "0", "Index": "1"}))
    links = response("")
    fake = FakeWSMan([physical, partitions, links], error=None)
    client, _ = make_client(fake)
    original = client._enumerate
    def enumerate_class(class_name, **kwargs):
        if class_name == "MSFT_PhysicalDisk":
            raise CIMError("protocol", "storage namespace unavailable")
        return original(class_name, **kwargs)
    client._enumerate = enumerate_class
    result = client.disk_inventory()
    assert result["physical_disks"]
    assert result["modern_physical_disks"] == []
    assert result["modern_status"] == "unavailable"


@pytest.mark.parametrize(("failed_method", "failed_stage"), [("physical_disks", "physical"), ("disk_partitions", "partitions"), ("logical_disk_partition_links", "links")])
def test_disk_inventory_logs_failed_stage_and_propagates_mandatory_errors(monkeypatch, caplog, failed_method, failed_stage):
    client, _ = make_client(FakeWSMan([]))
    error = CIMError("timeout", f"{failed_stage} failed")

    def fail_or_empty():
        if failed_method:
            raise error
        return []

    monkeypatch.setattr(client, "physical_disks", fail_or_empty if failed_method == "physical_disks" else lambda: [])
    monkeypatch.setattr(client, "disk_partitions", fail_or_empty if failed_method == "disk_partitions" else lambda: [])
    monkeypatch.setattr(client, "logical_disk_partition_links", fail_or_empty if failed_method == "logical_disk_partition_links" else lambda: [])
    with caplog.at_level("INFO"):
        with pytest.raises(CIMError) as exc:
            client.disk_inventory()
    assert exc.value is error
    record = next(record for record in caplog.records if record.message.startswith("windows_disk_inventory_timing"))
    assert f"failed_stage={failed_stage}" in record.message
    assert f"{failed_stage}:failed" in record.message
    assert "modern_ms=not_started" in record.message


def test_disk_inventory_timing_marks_optional_provider_failure_as_partial_success(caplog):
    client, _ = make_client(FakeWSMan([]))
    client.physical_disks = lambda: []
    client.disk_partitions = lambda: []
    client.logical_disk_partition_links = lambda: []
    client.modern_physical_disks = lambda: (_ for _ in ()).throw(CIMError("protocol", "storage unavailable"))
    with caplog.at_level("INFO"):
        result = client.disk_inventory()
    assert result["modern_status"] == "unavailable"
    record = next(record for record in caplog.records if record.message.startswith("windows_disk_inventory_timing"))
    assert "failed_stage=none" in record.message
    assert "outcome=partial_success" in record.message
    assert "modern:failed" in record.message


def test_storage_reliability_projection_and_case_insensitive_zero_values():
    reliability = response(node("MSFT_StorageReliabilityCounter", {
        "deviceid": "\\\\?\\disk0", "TEMPERATURE": "0", "TemperatureMax": "45",
        "Wear": "2", "PowerOnHours": "0", "UnsafeShutdownCount": "0",
    }))
    fake = FakeWSMan([reliability])
    client, _ = make_client(fake)
    result = client.storage_reliability_counters()[0]
    query = WindowsCIMClient._filter("MSFT_StorageReliabilityCounter").text
    assert all(field in query for field in ("DeviceId", "TemperatureMax", "ReadErrorsCorrected", "UnsafeShutdownCount"))
    assert result["Temperature"] == "0" and result["PowerOnHours"] == "0"


def test_storage_reliability_preserves_missing_and_invalid_values():
    fake = FakeWSMan([response(node("MSFT_StorageReliabilityCounter", {"DeviceId": "disk0", "Temperature": "bad", "Wear": "-1"}))])
    client, _ = make_client(fake)
    result = client.storage_reliability_counters()[0]
    assert result["Temperature"] == "bad" and result["Wear"] == "-1"


def test_processor_performance_falls_back_when_optional_projection_is_unsupported():
    client, _ = make_client(FakeWSMan([]))
    calls = []
    required = ET.fromstring(node("Win32_PerfFormattedData_PerfOS_Processor", {
        "Name": "_Total", "PercentProcessorTime": "17"
    }))

    def enumerate_class(class_name, **kwargs):
        calls.append(class_name)
        if class_name == "Win32_PerfFormattedData_PerfOS_Processor":
            raise CIMError("protocol", "optional counter rejected")
        return [required]

    client._enumerate = enumerate_class
    result = client.processor_performance()

    assert result[0].usage_percent == 17
    assert result[0].user_percent is None
    assert calls == ["Win32_PerfFormattedData_PerfOS_Processor", "Win32_PerfFormattedData_PerfOS_ProcessorRequired"]


def test_processor_performance_returns_collected_rows():
    fake = FakeWSMan([response(node("Win32_PerfFormattedData_PerfOS_Processor", {
        "Name": "_Total", "PercentProcessorTime": "5", "PercentUserTime": "2",
    }))])
    client, _ = make_client(fake)
    rows = client.processor_performance()
    assert len(rows) == 1
    assert rows[0].usage_percent == 5
    assert rows[0].user_percent == 2


def test_cpu_counter_projection_requests_all_supported_properties():
    query = WindowsCIMClient._filter("Win32_PerfFormattedData_PerfOS_Processor").text
    for field in ("PercentProcessorTime", "PercentUserTime", "PercentPrivilegedTime", "PercentIdleTime", "InterruptsPerSec"):
        assert field in query
    assert "ContextSwitchesPerSec" not in query
    assert "ContextSwitchesPerSec" in WindowsCIMClient._filter("Win32_PerfFormattedData_PerfOS_System").text


def test_cpu_performance_malformed_and_missing_counters_are_none_not_zero():
    fake = FakeWSMan([response(node("Win32_PerfFormattedData_PerfOS_Processor", {
        "Name": "_Total", "PercentProcessorTime": "7", "PercentUserTime": "bad",
        "PercentPrivilegedTime": "", "PercentIdleTime": "-1", "InterruptsPerSec": "oops",
    }))])
    client, _ = make_client(fake)
    row = client.processor_performance()[0]
    assert row.usage_percent == 7
    assert row.user_percent is None
    assert row.privileged_percent is None
    assert row.idle_percent is None
    assert row.interrupts_per_sec is None
    assert row.context_switches_per_sec is None


def test_cpu_counter_queries_are_allow_listed_and_missing_values_are_unavailable():
    assert "PercentUserTime" in WindowsCIMClient._filter("Win32_PerfFormattedData_PerfOS_Processor").text
    assert "ProcessorQueueLength" in WindowsCIMClient._filter("Win32_PerfFormattedData_PerfOS_System").text
    fake = FakeWSMan([response(node("Win32_PerfFormattedData_PerfOS_Processor", {"Name": "_Total", "PercentProcessorTime": "5"}))])
    client, _ = make_client(fake)
    row = client.processor_performance()[0]
    assert row.usage_percent == 5
    assert row.user_percent is None and row.interrupts_per_sec is None


def test_native_sensor_discovery_converts_acpi_and_marks_missing_classes_unsupported():
    temperature = node("Win32_TemperatureProbe", {"Name": "Board", "CurrentReading": "3000"})
    acpi = node("MSAcpi_ThermalZoneTemperature", {"InstanceName": "ACPI\\ThermalZone\\TZ00", "CurrentTemperature": "3100"})
    fake = FakeWSMan([response(temperature), response(""), response(""), response(acpi)])
    client, _ = make_client(fake)

    sensors = client.native_sensor_discovery()

    assert sensors[0]["value"] == 26.85
    assert sensors[0]["status"] == "ok"
    assert sensors[1]["status"] == "unsupported"
    assert sensors[3]["sensor_type"] == "thermal_zone"
    assert sensors[3]["value"] == 36.85
    assert sensors[3]["sensor_type"] != "cpu_package_temperature"


def test_native_sensor_discovery_marks_invalid_values_unavailable_and_permission_denied():
    invalid = node("Win32_TemperatureProbe", {"Name": "Board", "CurrentReading": "not-a-number"})
    fake = FakeWSMan([response(invalid)])
    client, _ = make_client(fake)
    sensors = client.native_sensor_discovery()
    assert sensors[0]["status"] == "unavailable"
    assert sensors[0]["error"] == "invalid_reading"


def test_operating_system_normalizes_extended_fields_and_dmtf_dates():
    fake = FakeWSMan([response(node("Win32_OperatingSystem", {
        "CSName": "WIN01", "Caption": "Windows 11 Pro", "Manufacturer": "Microsoft Corporation",
        "Version": "10.0", "BuildNumber": "26100", "OSArchitecture": "64-bit", "OSType": "18",
        "ProductType": "1", "InstallDate": "20240101120000.000000+330",
        "LastBootUpTime": "20261017145144.580916+330", "WindowsDirectory": "C:\\Windows",
        "SystemDirectory": "C:\\Windows\\System32", "SystemDrive": "C:", "BootDevice": "\\Device\\HarddiskVolume3",
        "Locale": "en-US", "CurrentTimeZone": "330", "ServicePackMajorVersion": "0",
        "TotalVisibleMemorySize": "1024", "FreePhysicalMemory": "512",
    }))])
    client, _ = make_client(fake)

    result = client.operating_system()[0]

    assert result.manufacturer == "Microsoft Corporation"
    assert result.build_number == "26100"
    assert result.architecture == "64-bit"
    assert result.install_date == "2024-01-01T06:30:00+00:00"
    assert result.last_boot_time == "2026-10-17T09:21:44.580916+00:00"
    assert result.time_zone == "330"


def test_invalid_dmtf_dates_become_unavailable():
    assert WindowsCIMClient._wmi_datetime("not-a-date") is None
    assert WindowsCIMClient._wmi_datetime("20261017145144.000000X330") is None


def test_os_timestamp_parser_accepts_timezone_aware_iso_and_rejects_naive():
    assert WindowsCIMClient._wmi_datetime("2026-10-17T14:51:44.5809165+05:30") == "2026-10-17T14:51:44.580916+05:30"
    assert WindowsCIMClient._wmi_datetime("2026-10-17T14:51:44") is None


def test_network_interfaces_join_adapter_configuration_and_counters_by_interface_identity():
    adapter = node("Win32_NetworkAdapter", {
        "Index": "12", "Name": "Ethernet 0", "Description": "Intel Ethernet",
        "MACAddress": "AA-BB-CC-DD-EE-FF", "NetConnectionStatus": "2", "Speed": "1000000000",
    })
    configuration = '<p:Win32_NetworkAdapterConfiguration xmlns:p="urn:test"><p:InterfaceIndex>12</p:InterfaceIndex><p:IPAddress>192.168.100.154</p:IPAddress><p:IPAddress>fe80::1%12</p:IPAddress><p:IPEnabled>true</p:IPEnabled></p:Win32_NetworkAdapterConfiguration>'
    counter = node("Win32_PerfFormattedData_Tcpip_NetworkInterface", {
        "Name": "Ethernet 0", "BytesReceivedPerSec": "1234", "BytesSentPerSec": "5678", "CurrentBandwidth": "1000000000",
    })
    fake = FakeWSMan([response(adapter), response(configuration), response(counter)])
    client, _ = make_client(fake)

    result = client.network_interfaces()

    assert result == [
        result[0].__class__(
            interface_index=12,
            name="Ethernet 0",
            description="Intel Ethernet",
            mac_address="AA-BB-CC-DD-EE-FF",
            ipv4_addresses=("192.168.100.154",),
            ipv6_addresses=("fe80::1%12",),
            interface_status="Connected",
            link_speed_bps=1_000_000_000,
            rx_bytes_per_sec=1234,
            tx_bytes_per_sec=5678,
            adapter_index=12,
        )
    ]


def test_network_interfaces_keep_unavailable_values_null_and_include_disconnected_adapters():
    adapter = node("Win32_NetworkAdapter", {"Index": "7", "Name": "Wi-Fi", "NetConnectionStatus": "7"})
    fake = FakeWSMan([response(adapter), response(""), response("")])
    client, _ = make_client(fake)

    result = client.network_interfaces()

    assert result[0].interface_index is None
    assert result[0].adapter_index == 7
    assert result[0].interface_status == "Disconnected"
    assert result[0].mac_address is None
    assert result[0].link_speed_bps is None
    assert result[0].rx_bytes_per_sec is None
    assert result[0].tx_bytes_per_sec is None


def test_network_interfaces_reject_windows_speed_sentinel_and_parse_nested_ip_arrays():
    adapter_one = node("Win32_NetworkAdapter", {
        "Index": "22", "Name": "Wi-Fi", "Description": "Wireless Adapter",
        "NetConnectionStatus": "2", "Speed": "9223372036854775807",
    })
    adapter_two = node("Win32_NetworkAdapter", {
        "Index": "5", "Name": "Ethernet", "Description": "Wired Adapter",
        "NetConnectionStatus": "2", "Speed": "100000000",
    })
    configuration_one = '<p:Win32_NetworkAdapterConfiguration xmlns:p="urn:test"><p:InterfaceIndex>22</p:InterfaceIndex><p:IPAddress><p:string>192.168.100.154</p:string><p:string>fe80::abcd%22</p:string></p:IPAddress><p:MACAddress>11-22-33-44-55-66</p:MACAddress></p:Win32_NetworkAdapterConfiguration>'
    configuration_two = '<p:Win32_NetworkAdapterConfiguration xmlns:p="urn:test"><p:InterfaceIndex>5</p:InterfaceIndex><p:IPAddress><p:string>10.0.0.5</p:string></p:IPAddress></p:Win32_NetworkAdapterConfiguration>'
    counter_one = node("Win32_PerfFormattedData_Tcpip_NetworkInterface", {
        "Name": "Wi-Fi", "BytesReceivedPersec": "2048", "BytesSentPersec": "1024", "CurrentBandwidth": "300000000",
    })
    counter_two = node("Win32_PerfFormattedData_Tcpip_NetworkInterface", {
        "Name": "Ethernet", "BytesReceivedPerSec": "4096", "BytesSentPerSec": "512",
    })
    # Responses are intentionally in a different order to prove joins do not use positions.
    fake = FakeWSMan([
        response(adapter_one + adapter_two),
        response(configuration_two + configuration_one),
        response(counter_two + counter_one),
    ])
    client, _ = make_client(fake)

    result = client.network_interfaces()
    wifi = next(item for item in result if item.interface_index == 22)
    ethernet = next(item for item in result if item.interface_index == 5)

    assert wifi.ipv4_addresses == ("192.168.100.154",)
    assert wifi.ipv6_addresses == ("fe80::abcd%22",)
    assert wifi.mac_address == "11-22-33-44-55-66"
    assert wifi.link_speed_bps == 300_000_000
    assert wifi.rx_bytes_per_sec == 2048 and wifi.tx_bytes_per_sec == 1024
    assert ethernet.ipv4_addresses == ("10.0.0.5",)
    assert ethernet.rx_bytes_per_sec == 4096 and ethernet.tx_bytes_per_sec == 512


def test_network_interfaces_preserve_adapter_index_and_map_configuration_interface_index():
    wifi = node("Win32_NetworkAdapter", {
        "Index": "0", "Name": "Wi-Fi", "Description": "Intel Wi-Fi", "NetConnectionStatus": "2",
    })
    ethernet = node("Win32_NetworkAdapter", {
        "Index": "2", "Name": "Ethernet", "Description": "Realtek Ethernet", "NetConnectionStatus": "7",
    })
    wifi_config = '<p:Win32_NetworkAdapterConfiguration xmlns:p="urn:test"><p:Index>0</p:Index><p:InterfaceIndex>18</p:InterfaceIndex><p:IPAddress><p:string>192.168.100.154</p:string><p:string>fe80::18</p:string></p:IPAddress><p:IPEnabled>true</p:IPEnabled></p:Win32_NetworkAdapterConfiguration>'
    ethernet_config = '<p:Win32_NetworkAdapterConfiguration xmlns:p="urn:test"><p:Index>2</p:Index><p:InterfaceIndex>4</p:InterfaceIndex><p:IPAddress><p:string>10.0.0.2</p:string></p:IPAddress><p:IPEnabled>false</p:IPEnabled></p:Win32_NetworkAdapterConfiguration>'
    wifi_counter = node("Win32_PerfFormattedData_Tcpip_NetworkInterface", {
        "Name": "Intel Wi-Fi", "BytesReceivedPerSec": "2048", "BytesSentPerSec": "1024",
    })
    fake = FakeWSMan([
        response(wifi + ethernet),
        response(ethernet_config + wifi_config),
        response(wifi_counter),
    ])
    client, _ = make_client(fake)

    result = client.network_interfaces()
    wifi_result = next(item for item in result if item.adapter_index == 0)
    ethernet_result = next(item for item in result if item.adapter_index == 2)

    assert wifi_result.interface_index == 18
    assert wifi_result.adapter_index == 0
    assert wifi_result.ipv4_addresses == ("192.168.100.154",)
    assert wifi_result.ipv6_addresses == ("fe80::18",)
    assert wifi_result.rx_bytes_per_sec == 2048
    assert wifi_result.tx_bytes_per_sec == 1024
    assert ethernet_result.interface_index == 4
    assert ethernet_result.adapter_index == 2


def test_network_interfaces_decode_wrapped_zero_index_ip_array_and_bracketed_perf_name():
    adapter = '<p:Win32_NetworkAdapter xmlns:p="urn:test"><p:Index><p:Value>0</p:Value></p:Index><p:Name><p:Value>Wi-Fi</p:Value></p:Name><p:Description><p:Value>Intel(R) Wi-Fi 6 AX201 160MHz</p:Value></p:Description><p:NetConnectionStatus><p:Value>2</p:Value></p:NetConnectionStatus></p:Win32_NetworkAdapter>'
    configuration = '<p:Win32_NetworkAdapterConfiguration xmlns:p="urn:test"><p:Index><p:Value>0</p:Value></p:Index><p:InterfaceIndex><p:Value>18</p:Value></p:InterfaceIndex><p:IPEnabled><p:Value>True</p:Value></p:IPEnabled><p:IPAddress><p:Value><p:string>192.168.100.154</p:string><p:string>fe80::1%18</p:string><p:string>2001:db8::18</p:string><p:string>fd00::18</p:string></p:Value></p:IPAddress></p:Win32_NetworkAdapterConfiguration>'
    performance = '<p:Win32_PerfFormattedData_Tcpip_NetworkInterface xmlns:p="urn:test"><p:Name><p:Value>Intel[R] Wi-Fi 6 AX201 160MHz</p:Value></p:Name><p:BytesReceivedPersec><p:Value>669</p:Value></p:BytesReceivedPersec><p:BytesSentPersec><p:Value>0</p:Value></p:BytesSentPersec></p:Win32_PerfFormattedData_Tcpip_NetworkInterface>'
    fake = FakeWSMan([response(adapter), response(configuration), response(performance)])
    client, _ = make_client(fake)

    result = client.network_interfaces()[0]

    assert result.adapter_index == 0
    assert result.interface_index == 18
    assert result.ipv4_addresses == ("192.168.100.154",)
    assert result.ipv6_addresses == ("fe80::1%18", "2001:db8::18", "fd00::18")
    assert result.rx_bytes_per_sec == 669
    assert result.tx_bytes_per_sec == 0


def test_network_configuration_query_requests_adapter_and_interface_indexes():
    query = WindowsCIMClient._filter("Win32_NetworkAdapterConfiguration").text

    assert query is not None
    assert "SELECT Index,InterfaceIndex," in query
    assert "IPAddress" in query
    assert "IPEnabled" in query


def test_network_interfaces_leave_ambiguous_performance_match_unavailable():
    adapter = node("Win32_NetworkAdapter", {"Index": "1", "Name": "Shared", "Description": "Shared", "NetConnectionStatus": "2"})
    configuration = node("Win32_NetworkAdapterConfiguration", {"Index": "1", "InterfaceIndex": "9"})
    first = node("Win32_PerfFormattedData_Tcpip_NetworkInterface", {"Name": "Shared", "BytesReceivedPersec": "10"})
    second = node("Win32_PerfFormattedData_Tcpip_NetworkInterface", {"Name": "Shared", "BytesReceivedPersec": "20"})
    fake = FakeWSMan([response(adapter), response(configuration), response(first + second)])
    client, _ = make_client(fake)

    result = client.network_interfaces()[0]

    assert result.interface_index == 9
    assert result.rx_bytes_per_sec is None


def test_multipage_and_empty_results():
    fake = FakeWSMan([response(node("x", {"CSName": "A", "Caption": "W", "Version": "1", "TotalVisibleMemorySize": "1", "FreePhysicalMemory": "1"}), "abc", False), response(node("x", {"CSName": "B", "Caption": "W", "Version": "2", "TotalVisibleMemorySize": "2", "FreePhysicalMemory": "1"}))])
    client, _ = make_client(fake)
    assert [x.hostname for x in client.operating_system()] == ["A", "B"]
    fake.pages = [response("")]
    assert client.processor() == []
    assert fake.calls[1][2] is not None

def test_empty_operating_system_result_is_safe_for_fetch_diagnostics():
    client, _ = make_client(FakeWSMan([response("")]))
    assert client.operating_system() == []


@pytest.mark.parametrize("error,category", [(AuthenticationError("secret-value"), "authentication"), (SSLError("secret-value"), "tls"), (Timeout("secret-value"), "timeout"), (PermissionError("secret-value"), "permission"), (WinRMTransportError("http", 500, "secret-value"), "transport"), (WSManFaultError(1, "m", "secret-value", "r"), "protocol")])
def test_transport_errors_are_sanitized(error, category):
    client, _ = make_client(FakeWSMan([], error=error))
    with pytest.raises(CIMError) as exc:
        client.processor()
    assert exc.value.category == category and "secret-value" not in str(exc.value)


def test_malformed_missing_context_and_faults_are_rejected():
    for page in ["<broken>", response("", None, False), body('<s:Body xmlns:s="http://www.w3.org/2003/05/soap-envelope"><s:Fault><x>bad</x></s:Fault></s:Body>')]:
        client, _ = make_client(FakeWSMan([page]))
        with pytest.raises(CIMError):
            client.processor()


def test_allowlist_limits_and_pull_does_not_send_max_elements():
    client, _ = make_client(FakeWSMan([response("")]))
    with pytest.raises(CIMError):
        client._enumerate("Win32_Bogus")
    limited, _ = make_client(FakeWSMan([response(node("x", {"Name": "_Total", "PercentProcessorTime": "1"}), "ctx", False), response(node("x", {"Name": "x", "PercentProcessorTime": "2"}))]), limits=CIMLimits(max_pages=1))
    with pytest.raises(CIMError):
        limited.processor()
    fake = FakeWSMan([response(node("x", {"Name": "_Total", "PercentProcessorTime": "1"}), "ctx", False), response("")])
    client, _ = make_client(fake)
    client.processor()
    assert fake.calls[1][2].tag.endswith("Pull")
    assert fake.calls[1][2][0].text == "ctx"
    assert all("MaxElements" not in str(call[2]) for call in fake.calls)


def test_response_and_data_limits_and_no_secret_disclosure():
    fake = FakeWSMan([response(node("x", {"Name": "_Total", "PercentProcessorTime": "1"}))])
    client, _ = make_client(fake, limits=CIMLimits(max_response_bytes=10))
    with pytest.raises(CIMError) as exc:
        client.processor()
    assert "secret-value" not in str(exc.value)


def test_usb_inventory_collects_controllers_hubs_and_associations():
    controller = node("Win32_USBController", {"DeviceID": "PCI\\VEN_8086&amp;DEV_9DED", "Name": "USB xHCI Controller", "Manufacturer": "Intel", "PNPDeviceID": "PCI\\VEN_8086&amp;DEV_9DED", "Status": "OK", "ConfigManagerErrorCode": "0"})
    hub = node("Win32_USBHub", {"DeviceID": "USB\\ROOT_HUB30", "Name": "USB Root Hub", "PNPDeviceID": "USB\\ROOT_HUB30", "Status": "OK"})
    association = node("Win32_USBControllerDevice", {"Antecedent": 'Win32_USBController.DeviceID="PCI\\\\VEN_8086&amp;DEV_9DED"', "Dependent": 'Win32_PnPEntity.DeviceID="USB\\\\VID_1234&amp;PID_ABCD\\\\SN1"'})
    device = node("Win32_PnPEntity", {"Name": "Example USB Device", "PNPDeviceID": "USB\\VID_1234&amp;PID_ABCD\\SN1", "PNPClass": "USB", "Manufacturer": "Example", "Status": "OK", "ConfigManagerErrorCode": "0", "Present": "true"})
    client, _ = make_client(FakeWSMan([response(controller), response(hub), response(association), response(device)]))
    result = client.usb_inventory()
    assert result["controllers"][0].name == "USB xHCI Controller"
    assert result["hubs"][0].name == "USB Root Hub"
    usb = result["devices"][0]
    assert usb.connection_state == "Unknown"
    assert usb.vendor_id == "1234" and usb.product_id == "ABCD"
    assert usb.controller_or_hub is not None


def test_usb_hub_cannot_process_filter_uses_fallback(monkeypatch):
    client, _ = make_client(FakeWSMan([response(""), response(""), response(""), response("")]))
    fallback = [USBHubResult(device_id="USB\\HUB1", name="Fallback hub", description=None, manufacturer=None, instance_id="USB\\HUB1", pnp_status="OK", config_manager_error_code=0)]
    monkeypatch.setattr(client, "_usb_hubs_powershell_fallback", lambda: fallback)
    original = client._enumerate
    def enumerate_with_hub_failure(class_name):
        if class_name == "Win32_USBHub":
            raise CIMError("protocol", "WSMan returned a protocol fault (n:CannotProcessFilter)")
        return original(class_name)
    monkeypatch.setattr(client, "_enumerate", enumerate_with_hub_failure)
    result = client.usb_inventory()
    assert [hub.name for hub in result["hubs"]] == ["Fallback hub"]
    assert "Win32_USBHub" not in result["errors"]


def test_usb_hub_fallback_failure_preserves_partial_inventory(monkeypatch):
    controller = node("Win32_USBController", {"DeviceID": "PCI\\C", "Name": "Controller", "Status": "OK"})
    device = node("Win32_PnPEntity", {"Name": "USB device", "PNPDeviceID": "USB\\VID_1234&amp;PID_0001", "PNPClass": "USB", "Status": "OK", "Present": "true"})
    client, _ = make_client(FakeWSMan([response(controller), response(""), response(device)]))
    monkeypatch.setattr(client, "_usb_hubs_powershell_fallback", lambda: (_ for _ in ()).throw(CIMError("protocol", "PowerShell USB hub query failed")))
    original = client._enumerate
    def enumerate_with_hub_failure(class_name):
        if class_name == "Win32_USBHub":
            raise CIMError("protocol", "WSMan returned a protocol fault (n:CannotProcessFilter)")
        return original(class_name)
    monkeypatch.setattr(client, "_enumerate", enumerate_with_hub_failure)
    result = client.usb_inventory()
    assert result["controllers"] and result["devices"]
    assert result["hubs"] == [] and result["errors"]["Win32_USBHub"] == "protocol"


def test_usb_controller_association_fallback_resolves_multiple_devices(monkeypatch):
    controller = node("Win32_USBController", {"DeviceID": "PCI\\C1", "PNPDeviceID": "PCI\\C1", "Name": "Controller 1", "Status": "OK"})
    device_one = node("Win32_PnPEntity", {"Name": "One", "PNPDeviceID": "USB\\D1", "PNPClass": "USB", "Present": "true"})
    device_two = node("Win32_PnPEntity", {"Name": "Two", "PNPDeviceID": "USB\\D2", "PNPClass": "USB", "Present": "true"})
    client, _ = make_client(FakeWSMan([response(controller), response(""), response(device_one + device_two)]))
    monkeypatch.setattr(client, "_usb_associations_powershell_fallback", lambda: [
        USBControllerDeviceResult('Win32_USBController.DeviceID="PCI\\\\C1"', 'Win32_PnPEntity.DeviceID="USB\\\\D1"'),
        USBControllerDeviceResult('Win32_USBController.DeviceID="PCI\\\\C1"', 'Win32_PnPEntity.DeviceID="USB\\\\D2"'),
    ])
    original = client._enumerate
    def enumerate_with_anonymous_associations(class_name):
        if class_name == "Win32_USBControllerDevice":
            return [ET.fromstring('<x><Antecedent>http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous</Antecedent><Dependent>http://schemas.xmlsoap.org/ws/2004/08/addressing/role/anonymous</Dependent></x>')]
        return original(class_name)
    monkeypatch.setattr(client, "_enumerate", enumerate_with_anonymous_associations)
    result = client.usb_inventory()
    assert [d.controller_or_hub for d in result["devices"]] == ["PCI\\C1", "PCI\\C1"]


def test_usb_controller_associations_leave_unmatched_and_malformed_records_unrelated(monkeypatch):
    controller = node("Win32_USBController", {"DeviceID": "PCI\\C1", "PNPDeviceID": "PCI\\C1", "Name": "Controller 1", "Status": "OK"})
    device = node("Win32_PnPEntity", {"Name": "One", "PNPDeviceID": "USB\\D1", "PNPClass": "USB", "Present": "true"})
    client, _ = make_client(FakeWSMan([response(controller), response(""), response(device)]))
    monkeypatch.setattr(client, "_usb_associations_powershell_fallback", lambda: [
        USBControllerDeviceResult('Win32_USBController.DeviceID="PCI\\\\UNKNOWN"', 'Win32_PnPEntity.DeviceID="USB\\\\D1"'),
        USBControllerDeviceResult("malformed", 'Win32_PnPEntity.DeviceID="USB\\\\MISSING"'),
    ])
    original = client._enumerate
    def enumerate_with_anonymous_associations(class_name):
        if class_name == "Win32_USBControllerDevice":
            return [ET.fromstring('<x><Antecedent>anonymous</Antecedent><Dependent>anonymous</Dependent></x>')]
        return original(class_name)
    monkeypatch.setattr(client, "_enumerate", enumerate_with_anonymous_associations)
    result = client.usb_inventory()
    assert result["devices"][0].controller_or_hub is None


def test_unrelated_usb_hub_error_does_not_use_fallback(monkeypatch):
    client, _ = make_client(FakeWSMan([response(""), response(""), response(""), response("")]))
    called = False
    def fallback():
        nonlocal called
        called = True
        return []
    monkeypatch.setattr(client, "_usb_hubs_powershell_fallback", fallback)
    original = client._enumerate
    def enumerate_with_hub_failure(class_name):
        if class_name == "Win32_USBHub":
            raise CIMError("timeout", "WSMan operation timed out")
        return original(class_name)
    monkeypatch.setattr(client, "_enumerate", enumerate_with_hub_failure)
    result = client.usb_inventory()
    assert not called and result["errors"]["Win32_USBHub"] == "timeout"


def test_usb_inventory_preserves_missing_optional_properties_and_unknown_status():
    device = node("Win32_PnPEntity", {"PNPDeviceID": "USB\\VID_0001&amp;PID_0002", "Status": "Degraded", "Present": "maybe", "ConfigManagerErrorCode": "not-a-number"})
    client, _ = make_client(FakeWSMan([response(""), response(""), response(""), response(device)]))
    usb = client.usb_inventory()["devices"][0]
    assert usb.name is None and usb.manufacturer is None
    assert usb.vendor_id == "0001" and usb.product_id == "0002"
    assert usb.config_manager_error_code is None
    assert usb.present is None and usb.connection_state == "Unknown"


def test_usb_inventory_allowlist_and_query_failure_are_isolated():
    query = WindowsCIMClient._filter("Win32_PnPEntity_USB").text
    assert "Win32_PnPEntity" in query and "PNPDeviceID" in query
    with pytest.raises(CIMError):
        WindowsCIMClient._filter("Win32_PnPEntity")
    client, _ = make_client(FakeWSMan([], error=Timeout("timed out")))
    result = client.usb_inventory()
    assert result["devices"] == []
    assert result["errors"]["Win32_USBController"] == "timeout"


def test_usb_inventory_normalizes_disabled_driver_error_and_storage():
    disabled = node("Win32_PnPEntity", {"Name": "Disabled", "PNPDeviceID": "USB\\VID_1234&amp;PID_0001", "PNPClass": "USB", "Status": "OK", "ConfigManagerErrorCode": "22", "Present": "true"})
    driver_error = node("Win32_PnPEntity", {"Name": "Broken", "PNPDeviceID": "USB\\VID_1234&amp;PID_0002", "PNPClass": "USB", "Status": "Error", "ConfigManagerErrorCode": "28", "Present": "true"})
    storage = node("Win32_PnPEntity", {"Name": "USB Disk", "PNPDeviceID": "USBSTOR\\VID_1234&amp;PID_0003", "PNPClass": "USB", "Service": "USBSTOR", "Status": "OK", "Present": "true"})
    client, _ = make_client(FakeWSMan([response(""), response(""), response(""), response(disabled + driver_error + storage)]))
    devices = client.usb_inventory()["devices"]
    assert devices[0].presence_state == "Present" and devices[0].driver_health == "Disabled"
    assert devices[1].driver_health == "DriverError"
    assert devices[2].device_type == "Storage" and devices[2].is_storage is True


def test_usb_inventory_preserves_generic_pnp_class():
    wpd = node("Win32_PnPEntity", {"Name": "Portable phone", "PNPDeviceID": "USB\\VID_18D1&amp;PID_4EE1", "PNPClass": "WPD", "Manufacturer": "Example", "Status": "OK", "Present": "true"})
    client, _ = make_client(FakeWSMan([response(""), response(""), response(""), response(wpd)]))
    device = client.usb_inventory()["devices"][0]
    assert device.device_class == "WPD"


def test_usb_inventory_deduplicates_same_instance_id_and_rejects_invalid_vid_pid():
    first = node("Win32_PnPEntity", {"Name": "One", "PNPDeviceID": "USB\\VID_12G4&amp;PID_0001", "PNPClass": "USB", "Present": "true"})
    duplicate = node("Win32_PnPEntity", {"Name": "One duplicate", "PNPDeviceID": "USB\\VID_12G4&amp;PID_0001", "PNPClass": "USB", "Present": "true"})
    client, _ = make_client(FakeWSMan([response(""), response(""), response(""), response(first + duplicate)]))
    devices = client.usb_inventory()["devices"]
    assert len(devices) == 1
    assert devices[0].vendor_id is None and devices[0].product_id == "0001"
