import re

from backend.windows_monitoring.cim import WindowsCIMClient

from tests.windows_cim_fixtures import FakeWSMan, make_client, node, response


def test_hardware_queries_are_fixed_and_do_not_request_sensitive_identifiers():
    expected = {
        "Win32_ComputerSystem": ("Manufacturer", "Model", "SystemType", "Domain", "Workgroup", "PartOfDomain", "NumberOfProcessors", "NumberOfLogicalProcessors"),
        "Win32_ComputerSystemProduct": ("Vendor", "Name", "Version"),
        "Win32_BaseBoard": ("Manufacturer", "Product", "Version"),
        "Win32_BIOS": ("Manufacturer", "SMBIOSBIOSVersion", "ReleaseDate"),
        "Win32_Processor": ("Name", "Manufacturer", "NumberOfCores", "NumberOfLogicalProcessors", "MaxClockSpeed"),
        "Win32_PhysicalMemory": ("Capacity", "Speed", "Manufacturer", "SMBIOSMemoryType", "DeviceLocator", "BankLabel"),
        "Win32_PhysicalMemoryArray": ("MaxCapacity", "MaxCapacityEx", "MemoryDevices", "Location", "Use"),
    }
    for class_name, fields in expected.items():
        query = WindowsCIMClient._filter(class_name).text
        assert query is not None
        assert all(field in query for field in fields)
        assert not re.search(r"UUID|SerialNumber|IdentifyingNumber", query, re.IGNORECASE)


def test_hardware_information_preserves_multiple_processors_and_memory_modules():
    fake = FakeWSMan([
        response(node("Win32_ComputerSystem", {
            "Manufacturer": "Contoso", "Model": "Rack X", "SystemType": "x64-based PC",
            "Domain": "example.test", "Workgroup": "WORKGROUP", "PartOfDomain": "TRUE",
            "NumberOfProcessors": "2", "NumberOfLogicalProcessors": "32",
        })),
        response(node("Win32_ComputerSystemProduct", {"Vendor": "Contoso", "Name": "Rack X", "Version": "1"})),
        response(node("Win32_BaseBoard", {"Manufacturer": "Board Co", "Product": "B1", "Version": "2"})),
        response(node("Win32_BIOS", {"Manufacturer": "Firmware Co", "SMBIOSBIOSVersion": "1.2", "ReleaseDate": "20240101120000.000000+000"})),
        response(node("Win32_Processor", {"Name": "CPU A", "Manufacturer": "Chip Co", "NumberOfCores": "8", "NumberOfLogicalProcessors": "16", "MaxClockSpeed": "3200"}) + node("Win32_Processor", {"Name": "CPU B", "Manufacturer": "Chip Co", "NumberOfCores": "8", "NumberOfLogicalProcessors": "16", "MaxClockSpeed": "3200"})),
        response(node("Win32_PhysicalMemory", {"Capacity": "17179869184", "Speed": "3200", "Manufacturer": "RAM Co", "SMBIOSMemoryType": "26", "DeviceLocator": "DIMM_A1", "BankLabel": "BANK 0"}) + node("Win32_PhysicalMemory", {"Capacity": "17179869184", "Speed": "3200", "Manufacturer": "RAM Co", "SMBIOSMemoryType": "26", "DeviceLocator": "DIMM_B1", "BankLabel": "BANK 1"})),
        response(node("Win32_PhysicalMemoryArray", {"MaxCapacity": "131072", "MemoryDevices": "8", "Location": "System Board", "Use": "3"})),
    ])
    client, _ = make_client(fake)

    result = client.hardware_information()

    assert len(result["processors"]) == 2
    assert result["processors"][0].max_clock_speed_mhz == 3200
    assert len(result["memory_modules"]) == 2
    assert result["memory_modules"][0].capacity_bytes == 17179869184
    assert result["memory_arrays"][0].max_capacity_bytes == 131072 * 1024
    assert result["bios"][0].release_date == "2024-01-01T12:00:00+00:00"


def test_memory_array_prefers_kib_interpretation_for_equal_raw_inconsistent_provider_values():
    fake = FakeWSMan([response(node("Win32_PhysicalMemoryArray", {
        "MaxCapacity": "33554432", "MaxCapacityEx": "33554432", "MemoryDevices": "2",
        "Location": "System Board", "Use": "3",
    }))])
    client, _ = make_client(fake)

    result = client.physical_memory_arrays()[0]

    assert result.max_capacity_bytes == 33554432 * 1024
    assert result.memory_devices == 2


def test_memory_array_prefers_max_capacity_ex_when_units_are_consistent():
    fake = FakeWSMan([response(node("Win32_PhysicalMemoryArray", {
        "MaxCapacity": "131072", "MaxCapacityEx": str(131072 * 1024), "MemoryDevices": "8",
    }))])
    client, _ = make_client(fake)

    assert client.physical_memory_arrays()[0].max_capacity_bytes == 131072 * 1024


def test_memory_array_capacity_handles_missing_zero_and_unusually_large_values():
    assert WindowsCIMClient._memory_array_capacity_bytes(0, 0) is None
    assert WindowsCIMClient._memory_array_capacity_bytes(None, 34359738368) == 34359738368
    assert WindowsCIMClient._memory_array_capacity_bytes(2**50, None) == 2**50 * 1024


def test_hardware_normalization_keeps_unsupported_and_invalid_values_unavailable():
    fake = FakeWSMan([
        response(node("Win32_ComputerSystem", {"PartOfDomain": "unknown", "NumberOfProcessors": "bad"})),
        response(node("Win32_ComputerSystemProduct", {})),
        response(node("Win32_BaseBoard", {})),
        response(node("Win32_BIOS", {"ReleaseDate": "not-a-date"})),
        response(node("Win32_Processor", {"NumberOfCores": "-1"})),
        response(node("Win32_PhysicalMemory", {"Capacity": "", "Speed": "bad"})),
        response(node("Win32_PhysicalMemoryArray", {"MaxCapacityEx": "bad", "MaxCapacity": "bad"})),
    ])
    client, _ = make_client(fake)

    result = client.hardware_information()

    assert result["computer_system"][0].part_of_domain is None
    assert result["computer_system"][0].number_of_processors is None
    assert result["bios"][0].release_date is None
    assert result["processors"][0].number_of_cores is None
    assert result["memory_modules"][0].capacity_bytes is None
    assert result["memory_arrays"][0].max_capacity_bytes is None


def test_hardware_collection_respects_existing_item_limit():
    fake = FakeWSMan([response(node("Win32_Processor", {"Name": "CPU"}) * 2)])
    client, _ = make_client(fake)
    client.limits = client.limits.__class__(max_items=1)

    try:
        client.hardware_processors()
    except Exception as exc:
        assert exc.__class__.__name__ == "CIMError"
    else:
        raise AssertionError("expected item limit failure")
