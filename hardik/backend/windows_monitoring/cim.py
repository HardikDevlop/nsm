"""Read-only, allow-listed CIM enumeration over verified WSMan."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import ipaddress
import logging
import re
from time import perf_counter
from typing import Any, Callable
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

from pypsrp.exceptions import AuthenticationError, WinRMTransportError, WSManFaultError
from pypsrp.wsman import WSMan, NAMESPACES
from requests.exceptions import SSLError, Timeout
from .sensors import stable_sensor_id


_HOSTNAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,253}[A-Za-z0-9])?$")
_CIM_URI = "http://schemas.microsoft.com/wbem/wsman/1/wmi/root/cimv2/*"
_WMI_URI = "http://schemas.microsoft.com/wbem/wsman/1/wmi/root/wmi/*"
_STORAGE_URI = "http://schemas.microsoft.com/wbem/wsman/1/wmi/root/microsoft/windows/storage/*"
_WQL_DIALECT = "http://schemas.microsoft.com/wbem/wsman/1/WQL"
_FILTER_CLASS = {
    "Win32_OperatingSystem": "SELECT Caption,Manufacturer,Version,BuildNumber,OSArchitecture,OSType,ProductType,InstallDate,LastBootUpTime,WindowsDirectory,SystemDirectory,SystemDrive,BootDevice,Locale,CurrentTimeZone,ServicePackMajorVersion,ServicePackMinorVersion,CSName,TotalVisibleMemorySize,FreePhysicalMemory FROM Win32_OperatingSystem",
    "Win32_PerfFormattedData_PerfDisk_LogicalDisk": "SELECT Name,DiskReadsPerSec,DiskWritesPerSec,DiskTransfersPerSec,DiskReadBytesPerSec,DiskWriteBytesPerSec,DiskBytesPerSec,AvgDiskSecPerRead,AvgDiskSecPerWrite,AvgDiskSecPerTransfer,AvgDiskQueueLength,CurrentDiskQueueLength,SplitIOPerSec,PercentDiskTime FROM Win32_PerfFormattedData_PerfDisk_LogicalDisk",
    "Win32_PerfFormattedData_PerfDisk_PhysicalDisk": "SELECT Name,DiskReadsPerSec,DiskWritesPerSec,DiskTransfersPerSec,DiskReadBytesPerSec,DiskWriteBytesPerSec,DiskBytesPerSec,AvgDiskSecPerRead,AvgDiskSecPerWrite,AvgDiskSecPerTransfer,AvgDiskQueueLength,CurrentDiskQueueLength,SplitIOPerSec,PercentDiskTime FROM Win32_PerfFormattedData_PerfDisk_PhysicalDisk",
    "Win32_PerfFormattedData_PerfOS_Processor": "SELECT Name,PercentProcessorTime,PercentUserTime,PercentPrivilegedTime,PercentIdleTime,InterruptsPerSec FROM Win32_PerfFormattedData_PerfOS_Processor",
    "Win32_PerfFormattedData_PerfOS_ProcessorRequired": "SELECT Name,PercentProcessorTime FROM Win32_PerfFormattedData_PerfOS_Processor",
    "Win32_PerfFormattedData_PerfOS_System": "SELECT ProcessorQueueLength,ContextSwitchesPerSec FROM Win32_PerfFormattedData_PerfOS_System",
    "Win32_PerfFormattedData_PerfOS_Memory": "SELECT AvailableMBytes,PagesPersec,PageReadsPersec,PageWritesPersec,PageFaultsPersec,CommittedBytes,CommitLimit,CacheBytes,PoolPagedBytes,PoolNonpagedBytes,PercentCommittedBytesInUse FROM Win32_PerfFormattedData_PerfOS_Memory",
    "Win32_TemperatureProbe": "SELECT Name,CurrentReading,Status,Availability FROM Win32_TemperatureProbe",
    "Win32_Fan": "SELECT Name,DesiredSpeed,Status,Availability FROM Win32_Fan",
    "Win32_VoltageProbe": "SELECT Name,CurrentReading,Status,Availability FROM Win32_VoltageProbe",
    "MSAcpi_ThermalZoneTemperature": "SELECT InstanceName,CurrentTemperature,Active,Passive FROM MSAcpi_ThermalZoneTemperature",
    "LibreHardwareMonitor_Sensor": "SELECT Identifier,Name,Value,SensorType,HardwareId,Hardware,Parent,Instance,Min,Max FROM Sensor",
    "Win32_LogicalDisk": "SELECT DeviceID,Size,FreeSpace,VolumeName FROM Win32_LogicalDisk WHERE DriveType = 3",
    "Win32_DiskDrive": "SELECT DeviceID,Index,Model,SerialNumber,PNPDeviceID,InterfaceType,MediaType,Size,FirmwareRevision,Status,Partitions,BytesPerSector FROM Win32_DiskDrive",
    "Win32_DiskPartition": "SELECT DeviceID,DiskIndex,Index,Name,Size,StartingOffset,Type,BootPartition,PrimaryPartition FROM Win32_DiskPartition",
    "Win32_LogicalDiskToPartition": "SELECT Antecedent,Dependent FROM Win32_LogicalDiskToPartition",
    "MSFT_PhysicalDisk": "SELECT FriendlyName,MediaType,BusType,HealthStatus,OperationalStatus,Size,FirmwareVersion,SerialNumber,UniqueId,DeviceId FROM MSFT_PhysicalDisk",
    "MSFT_StorageReliabilityCounter": "SELECT DeviceId,Temperature,TemperatureMax,Wear,ReadErrorsTotal,WriteErrorsTotal,ReadErrorsCorrected,WriteErrorsCorrected,PowerOnHours,UnsafeShutdownCount FROM MSFT_StorageReliabilityCounter",
    "Win32_NetworkAdapter": "SELECT Index,Name,Description,MACAddress,NetConnectionStatus,Speed,PhysicalAdapter FROM Win32_NetworkAdapter",
    "Win32_NetworkAdapterConfiguration": "SELECT Index,InterfaceIndex,Description,MACAddress,IPAddress,IPEnabled FROM Win32_NetworkAdapterConfiguration",
    "Win32_PerfFormattedData_Tcpip_NetworkInterface": "SELECT Name,BytesReceivedPerSec,BytesSentPerSec,CurrentBandwidth FROM Win32_PerfFormattedData_Tcpip_NetworkInterface",
    "Win32_Service": "SELECT Name,DisplayName,State,StartMode,ProcessId FROM Win32_Service",
    "Win32_Process": "SELECT Name,ProcessId,WorkingSetSize FROM Win32_Process",
    "Win32_NTLogEvent": "SELECT TimeGenerated,EventCode,Type,SourceName,Logfile,Message FROM Win32_NTLogEvent",
    "Win32_ComputerSystem": "SELECT Manufacturer,Model,SystemType,Domain,Workgroup,PartOfDomain,NumberOfProcessors,NumberOfLogicalProcessors FROM Win32_ComputerSystem",
    "Win32_ComputerSystemProduct": "SELECT Vendor,Name,Version FROM Win32_ComputerSystemProduct",
    "Win32_BaseBoard": "SELECT Manufacturer,Product,Version FROM Win32_BaseBoard",
    "Win32_BIOS": "SELECT Manufacturer,SMBIOSBIOSVersion,ReleaseDate FROM Win32_BIOS",
    "Win32_Processor": "SELECT Name,Manufacturer,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed FROM Win32_Processor",
    "Win32_PhysicalMemory": "SELECT Capacity,Speed,Manufacturer,SMBIOSMemoryType,DeviceLocator,BankLabel FROM Win32_PhysicalMemory",
    "Win32_PhysicalMemoryArray": "SELECT MaxCapacity,MaxCapacityEx,MemoryDevices,Location,Use FROM Win32_PhysicalMemoryArray",
}
_MAX_XML_BYTES = 1_000_000
logger = logging.getLogger(__name__)


class CIMError(Exception):
    """Sanitized adapter error with a stable category."""

    def __init__(self, category: str, message: str, *, stage: str = "cim"):
        super().__init__(message)
        self.category = category
        self.message = message
        self.stage = stage


@dataclass(frozen=True)
class OperatingSystemResult:
    hostname: str
    caption: str
    version: str
    total_memory_bytes: int
    free_memory_bytes: int
    manufacturer: str | None = None
    build_number: str | None = None
    architecture: str | None = None
    os_type: int | None = None
    product_type: int | None = None
    install_date: str | None = None
    last_boot_time: str | None = None
    windows_directory: str | None = None
    system_directory: str | None = None
    system_drive: str | None = None
    boot_device: str | None = None
    locale: str | None = None
    time_zone: str | None = None
    service_pack: str | None = None


@dataclass(frozen=True)
class ProcessorResult:
    name: str
    percent_processor_time: float

@dataclass(frozen=True)
class ProcessorPerformanceResult:
    name: str
    usage_percent: float | None
    user_percent: float | None
    privileged_percent: float | None
    idle_percent: float | None
    interrupts_per_sec: float | None
    context_switches_per_sec: float | None

@dataclass(frozen=True)
class SystemPerformanceResult:
    processor_queue_length: float | None
    context_switches_per_sec: float | None

@dataclass(frozen=True)
class MemoryPerformanceResult:
    available_mbytes: float | None
    pages_per_sec: float | None
    page_reads_per_sec: float | None
    page_writes_per_sec: float | None
    page_faults_per_sec: float | None
    committed_bytes: float | None
    commit_limit: float | None
    cache_bytes: float | None
    pool_paged_bytes: float | None
    pool_nonpaged_bytes: float | None
    percent_committed_bytes_in_use: float | None

@dataclass(frozen=True)
class DiskResult:
    device_id: str
    size_bytes: int
    free_bytes: int
    volume_name: str

@dataclass(frozen=True)
class PhysicalDiskResult:
    device_id: str | None
    index: int | None
    model: str | None
    serial_number: str | None
    pnp_device_id: str | None
    interface_type: str | None
    media_type: str | None
    size_bytes: int | None
    firmware_revision: str | None
    status: str | None
    partitions: int | None
    bytes_per_sector: int | None

@dataclass(frozen=True)
class DiskPartitionResult:
    device_id: str | None
    disk_index: int | None
    index: int | None
    name: str | None
    size_bytes: int | None
    starting_offset: int | None
    partition_type: str | None
    boot_partition: bool | None
    primary_partition: bool | None

@dataclass(frozen=True)
class DiskPerformanceResult:
    instance: str
    read_iops: float | None
    write_iops: float | None
    total_iops: float | None
    read_bytes_per_sec: float | None
    write_bytes_per_sec: float | None
    total_bytes_per_sec: float | None
    read_latency_ms: float | None
    write_latency_ms: float | None
    average_latency_ms: float | None
    average_queue_length: float | None
    current_queue_length: float | None
    split_io_per_sec: float | None
    percent_disk_time: float | None


@dataclass(frozen=True)
class NetworkInterfaceResult:
    interface_index: int | None
    name: str | None
    description: str | None
    mac_address: str | None
    ipv4_addresses: tuple[str, ...]
    ipv6_addresses: tuple[str, ...]
    interface_status: str | None
    link_speed_bps: int | None
    rx_bytes_per_sec: int | None
    tx_bytes_per_sec: int | None
    adapter_index: int | None = None


@dataclass(frozen=True)
class ComputerSystemResult:
    manufacturer: str | None
    model: str | None
    system_type: str | None
    domain: str | None
    workgroup: str | None
    part_of_domain: bool | None
    number_of_processors: int | None
    number_of_logical_processors: int | None


@dataclass(frozen=True)
class ComputerSystemProductResult:
    vendor: str | None
    name: str | None
    version: str | None


@dataclass(frozen=True)
class BaseBoardResult:
    manufacturer: str | None
    product: str | None
    version: str | None


@dataclass(frozen=True)
class BIOSResult:
    manufacturer: str | None
    smbios_bios_version: str | None
    release_date: str | None


@dataclass(frozen=True)
class HardwareProcessorResult:
    name: str | None
    manufacturer: str | None
    number_of_cores: int | None
    number_of_logical_processors: int | None
    max_clock_speed_mhz: int | None


@dataclass(frozen=True)
class PhysicalMemoryResult:
    capacity_bytes: int | None
    speed_mhz: int | None
    manufacturer: str | None
    smbios_memory_type: int | None
    device_locator: str | None
    bank_label: str | None


@dataclass(frozen=True)
class PhysicalMemoryArrayResult:
    max_capacity_bytes: int | None
    memory_devices: int | None
    location: str | None
    use: int | None


@dataclass(frozen=True)
class CIMLimits:
    max_pages: int = 64
    max_items: int = 32
    max_response_bytes: int = _MAX_XML_BYTES


def _validate_target(hostname: str, port: int) -> None:
    if not isinstance(hostname, str) or not hostname or hostname != hostname.strip():
        raise ValueError("hostname must be a bare host or IP address")
    if urlparse(hostname).scheme or "/" in hostname or "://" in hostname:
        raise ValueError("hostname must not contain a URL or path")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        if not _HOSTNAME.fullmatch(hostname):
            raise ValueError("malformed hostname") from None
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")


class WindowsCIMClient:
    """Enumerate two fixed CIM classes using HTTPS WSMan only."""

    def __init__(
        self,
        hostname: str,
        username: str,
        password: str,
        *,
        port: int = 5986,
        trusted_ca_path: str | None = None,
        connection_timeout: int = 10,
        read_timeout: int = 20,
        operation_timeout: int = 20,
        limits: CIMLimits | None = None,
        wsman_factory: Callable[..., Any] | None = None,
    ) -> None:
        _validate_target(hostname, port)
        if not username or not password:
            raise ValueError("username and password are required")
        if any(value <= 0 for value in (connection_timeout, read_timeout, operation_timeout)):
            raise ValueError("timeouts must be positive")
        self.hostname = hostname
        self.username = username
        self._password = password
        self.port = port
        self.trusted_ca_path = trusted_ca_path
        self.connection_timeout = connection_timeout
        self.read_timeout = read_timeout
        self.operation_timeout = operation_timeout
        self.limits = limits or CIMLimits()
        if self.limits.max_pages <= 0 or self.limits.max_items <= 0 or self.limits.max_response_bytes <= 0:
            raise ValueError("CIM limits must be positive")
        self._wsman_factory = wsman_factory or WSMan

    def _new_wsman(self) -> Any:
        return self._wsman_factory(
            self.hostname,
            port=self.port,
            username=self.username,
            password=self._password,
            ssl=True,
            auth="ntlm",
            cert_validation=self.trusted_ca_path or True,
            connection_timeout=self.connection_timeout,
            read_timeout=self.read_timeout,
            operation_timeout=self.operation_timeout,
            path="wsman",
        )

    @staticmethod
    def _filter(class_name: str) -> ET.Element:
        if class_name not in _FILTER_CLASS:
            raise CIMError("permission", "CIM class is not allowed")
        node = ET.Element("{http://schemas.xmlsoap.org/ws/2004/09/enumeration}Filter", {"Dialect": _WQL_DIALECT})
        node.text = _FILTER_CLASS[class_name]
        return node

    @staticmethod
    def _text(node: ET.Element, name: str) -> str:
        for child in list(node):
            if child.tag.rsplit("}", 1)[-1] == name:
                direct = (child.text or "").strip()
                if direct:
                    return direct
                for descendant in child.iter():
                    if descendant is not child and not list(descendant):
                        value = (descendant.text or "").strip()
                        if value:
                            return value
        return ""

    @staticmethod
    def _counter_text(node: ET.Element, name: str) -> str:
        """Read performance-counter properties without depending on casing."""
        wanted = name.casefold()
        for child in list(node):
            if child.tag.rsplit("}", 1)[-1].casefold() != wanted:
                continue
            direct = (child.text or "").strip()
            if direct:
                return direct
            for descendant in child.iter():
                if descendant is not child and not list(descendant):
                    value = (descendant.text or "").strip()
                    if value:
                        return value
        return ""

    @staticmethod
    def _texts(node: ET.Element, name: str) -> list[str]:
        values: list[str] = []
        for child in list(node):
            if child.tag.rsplit("}", 1)[-1] != name:
                continue
            direct = (child.text or "").strip()
            if direct:
                values.append(direct)
            else:
                values.extend(
                    text.strip()
                    for descendant in child.iter()
                    if descendant is not child
                    for text in [(descendant.text or "")]
                    if text.strip() and not list(descendant)
                )
        return values

    @staticmethod
    def _first_text(node: ET.Element | None, *names: str) -> str:
        if node is None:
            return ""
        for name in names:
            value = WindowsCIMClient._text(node, name)
            if value:
                return value
        return ""

    @staticmethod
    def _optional_int(value: str) -> int | None:
        try:
            return int(value) if value else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _optional_positive_int(value: str) -> int | None:
        parsed = WindowsCIMClient._optional_int(value)
        # Windows uses signed/unsigned all-bits-set values for unavailable
        # numeric properties, notably Win32_NetworkAdapter.Speed.
        sentinels = {2**63 - 1, 2**64 - 1}
        return parsed if parsed is not None and parsed >= 0 and parsed not in sentinels else None

    @staticmethod
    def _optional_bool(value: str) -> bool | None:
        if not value:
            return None
        normalized = value.strip().casefold()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
        return None

    @staticmethod
    def _wmi_datetime(value: str) -> str | None:
        """Normalize a WMI DMTF timestamp without assuming local time."""
        if not value:
            return None
        try:
            # Some CIM/PSRP serializers emit an ISO value instead of DMTF.
            if "T" in value:
                iso_value = value.replace("Z", "+00:00")
                iso_value = re.sub(r"(\.\d{6})\d+(?=[+-]\d{2}:\d{2}$)", r"\1", iso_value)
                parsed = datetime.fromisoformat(iso_value)
                return parsed.isoformat() if parsed.tzinfo is not None else None
            if len(value) < 25 or value[14] != ".":
                return None
            base = datetime.strptime(value[:14], "%Y%m%d%H%M%S")
            micros = int(value[15:21])
            sign = value[21:22]
            offset = value[22:25]
            if len(offset) != 3 or not offset.isdigit() or sign not in {"+", "-"}:
                return None
            minutes = int(offset)
            if sign == "-":
                minutes = -minutes
            return (base.replace(microsecond=micros, tzinfo=timezone.utc) - timedelta(minutes=minutes)).isoformat()
        except (TypeError, ValueError, OverflowError):
            return None

    @staticmethod
    def _identity(value: str) -> str:
        # WMI/performance providers can encode the same parenthesized token
        # with either round or square brackets, e.g. Intel(R) vs Intel[R].
        normalized = re.sub(r"[()\[\]]", "", value or "")
        return re.sub(r"\s+", " ", normalized).strip().casefold()

    @staticmethod
    def _addresses(node: ET.Element) -> tuple[tuple[str, ...], tuple[str, ...]]:
        ipv4: list[str] = []
        ipv6: list[str] = []
        for address in WindowsCIMClient._texts(node, "IPAddress"):
            try:
                parsed = ipaddress.ip_address(address.split("%", 1)[0])
            except ValueError:
                continue
            (ipv4 if parsed.version == 4 else ipv6).append(address)
        return tuple(ipv4), tuple(ipv6)

    def _parse_items(self, body: ET.Element) -> list[ET.Element]:
        raw = ET.tostring(body, encoding="utf-8")
        if len(raw) > self.limits.max_response_bytes:
            raise CIMError("protocol", "WSMan response exceeded the configured limit")
        fault = body.find(".//s:Fault", NAMESPACES)
        if fault is not None:
            raise CIMError("protocol", "WSMan returned a SOAP fault")
        # Enumeration responses place Items in the enumeration namespace;
        # XmlFragment payloads inside it carry the CIM properties.
        items = body.findall(".//wsen:Items/*", NAMESPACES)
        if len(items) > self.limits.max_items:
            raise CIMError("protocol", "WSMan item limit exceeded")
        return items

    def _enumerate(self, class_name: str, *, namespace: str = "root/cimv2") -> list[ET.Element]:
        wsman = self._new_wsman()
        resource_uri = _WMI_URI if namespace == "root/wmi" else _STORAGE_URI if namespace.casefold() == "root/microsoft/windows/storage" else _CIM_URI
        try:
            enumerate_request = ET.Element("{http://schemas.xmlsoap.org/ws/2004/09/enumeration}Enumerate")
            enumerate_request.append(self._filter(class_name))
            body = wsman.enumerate(resource_uri, resource=enumerate_request, timeout=self.operation_timeout)
            if body is None or not isinstance(body, ET.Element):
                raise CIMError("parsing", "Malformed WSMan enumeration response")
            result = self._parse_items(body)
            context = body.find(".//wsen:EnumerationContext", NAMESPACES)
            eos = body.find(".//wsen:EndOfSequence", NAMESPACES) is not None
            if context is None and not eos:
                raise CIMError("parsing", "WSMan response omitted enumeration context")
            pages = 1
            while context is not None and not eos:
                if pages >= self.limits.max_pages:
                    raise CIMError("protocol", "WSMan page limit exceeded")
                # Deliberately omit MaxElements: this host rejects that Pull override.
                pull_request = ET.Element("{http://schemas.xmlsoap.org/ws/2004/09/enumeration}Pull")
                pull_request.append(context)
                body = wsman.pull(resource_uri, resource=pull_request, timeout=self.operation_timeout)
                if body is None or not isinstance(body, ET.Element):
                    raise CIMError("parsing", "Malformed WSMan pull response")
                result.extend(self._parse_items(body))
                if len(result) > self.limits.max_items:
                    raise CIMError("protocol", "WSMan item limit exceeded")
                context = body.find(".//wsen:EnumerationContext", NAMESPACES)
                eos = body.find(".//wsen:EndOfSequence", NAMESPACES) is not None
                if context is None and not eos:
                    raise CIMError("parsing", "WSMan response omitted enumeration context")
                pages += 1
            return result
        except CIMError:
            raise
        except (AuthenticationError,):
            raise CIMError("authentication", "WSMan authentication failed") from None
        except SSLError:
            raise CIMError("tls", "TLS certificate validation failed") from None
        except Timeout:
            raise CIMError("timeout", "WSMan operation timed out") from None
        except WSManFaultError as exc:
            # Keep diagnostics bounded and free of credentials/identifiers. The
            # fault code helps distinguish unsupported classes from provider
            # failures without exposing the raw SOAP payload.
            fault_code = getattr(exc, "code", None) or getattr(exc, "fault_code", None)
            suffix = f" ({str(fault_code)[:80]})" if fault_code else ""
            raise CIMError("protocol", f"WSMan returned a protocol fault{suffix}") from None
        except PermissionError:
            raise CIMError("permission", "WSMan permission denied") from None
        except WinRMTransportError:
            raise CIMError("transport", "WSMan transport failed") from None
        except (ET.ParseError, ValueError, TypeError):
            raise CIMError("parsing", "Malformed WSMan response") from None
        except Exception:
            raise CIMError("protocol", "WSMan request failed") from None
        finally:
            close = getattr(wsman, "close", None)
            if callable(close):
                close()

    def operating_system(self) -> list[OperatingSystemResult]:
        results = []
        for node in self._enumerate("Win32_OperatingSystem"):
            try:
                total_kib = int(self._text(node, "TotalVisibleMemorySize"))
                free_kib = int(self._text(node, "FreePhysicalMemory"))
                install_date = self._wmi_datetime(self._text(node, "InstallDate"))
                last_boot_time = self._wmi_datetime(self._text(node, "LastBootUpTime"))
                timezone_minutes = self._optional_int(self._text(node, "CurrentTimeZone"))
                results.append(OperatingSystemResult(
                    self._text(node, "CSName"), self._text(node, "Caption"), self._text(node, "Version"), total_kib * 1024, free_kib * 1024,
                    manufacturer=self._text(node, "Manufacturer") or None,
                    build_number=self._text(node, "BuildNumber") or None,
                    architecture=self._text(node, "OSArchitecture") or None,
                    os_type=self._optional_int(self._text(node, "OSType")),
                    product_type=self._optional_int(self._text(node, "ProductType")),
                    install_date=install_date,
                    last_boot_time=last_boot_time,
                    windows_directory=self._text(node, "WindowsDirectory") or None,
                    system_directory=self._text(node, "SystemDirectory") or None,
                    system_drive=self._text(node, "SystemDrive") or None,
                    boot_device=self._text(node, "BootDevice") or None,
                    locale=self._text(node, "Locale") or None,
                    time_zone=str(timezone_minutes) if timezone_minutes is not None else None,
                    service_pack=(self._text(node, "ServicePackMajorVersion") or self._text(node, "ServicePackMinorVersion") or None),
                ))
            except (TypeError, ValueError):
                raise CIMError("parsing", "Invalid Windows operating-system data") from None
        return results

    def computer_system(self) -> list[ComputerSystemResult]:
        return [ComputerSystemResult(
            manufacturer=self._text(node, "Manufacturer") or None,
            model=self._text(node, "Model") or None,
            system_type=self._text(node, "SystemType") or None,
            domain=self._text(node, "Domain") or None,
            workgroup=self._text(node, "Workgroup") or None,
            part_of_domain=self._optional_bool(self._text(node, "PartOfDomain")),
            number_of_processors=self._optional_positive_int(self._text(node, "NumberOfProcessors")),
            number_of_logical_processors=self._optional_positive_int(self._text(node, "NumberOfLogicalProcessors")),
        ) for node in self._enumerate("Win32_ComputerSystem")]

    def computer_system_product(self) -> list[ComputerSystemProductResult]:
        return [ComputerSystemProductResult(
            vendor=self._text(node, "Vendor") or None,
            name=self._text(node, "Name") or None,
            version=self._text(node, "Version") or None,
        ) for node in self._enumerate("Win32_ComputerSystemProduct")]

    def baseboard(self) -> list[BaseBoardResult]:
        return [BaseBoardResult(
            manufacturer=self._text(node, "Manufacturer") or None,
            product=self._text(node, "Product") or None,
            version=self._text(node, "Version") or None,
        ) for node in self._enumerate("Win32_BaseBoard")]

    def bios(self) -> list[BIOSResult]:
        return [BIOSResult(
            manufacturer=self._text(node, "Manufacturer") or None,
            smbios_bios_version=self._text(node, "SMBIOSBIOSVersion") or None,
            release_date=self._wmi_datetime(self._text(node, "ReleaseDate")),
        ) for node in self._enumerate("Win32_BIOS")]

    def hardware_processors(self) -> list[HardwareProcessorResult]:
        return [HardwareProcessorResult(
            name=self._text(node, "Name") or None,
            manufacturer=self._text(node, "Manufacturer") or None,
            number_of_cores=self._optional_positive_int(self._text(node, "NumberOfCores")),
            number_of_logical_processors=self._optional_positive_int(self._text(node, "NumberOfLogicalProcessors")),
            max_clock_speed_mhz=self._optional_positive_int(self._text(node, "MaxClockSpeed")),
        ) for node in self._enumerate("Win32_Processor")]

    def physical_memory(self) -> list[PhysicalMemoryResult]:
        return [PhysicalMemoryResult(
            capacity_bytes=(self._optional_positive_int(self._text(node, "Capacity"))),
            speed_mhz=self._optional_positive_int(self._text(node, "Speed")),
            manufacturer=self._text(node, "Manufacturer") or None,
            smbios_memory_type=self._optional_positive_int(self._text(node, "SMBIOSMemoryType")),
            device_locator=self._text(node, "DeviceLocator") or None,
            bank_label=self._text(node, "BankLabel") or None,
        ) for node in self._enumerate("Win32_PhysicalMemory")]

    @staticmethod
    def _memory_array_capacity_bytes(max_capacity_kib: int | None, max_capacity_ex: int | None) -> int | None:
        """Normalize the two Windows memory-array capacity properties.

        Win32_PhysicalMemoryArray.MaxCapacity is KiB; MaxCapacityEx is bytes.
        A few providers return the same raw number for both properties, which
        is inconsistent with those documented units. In that case the KiB
        value is the supported interpretation. Otherwise a valid Ex value is
        preferred, with MaxCapacity as the compatibility fallback.
        """
        if max_capacity_kib is not None and max_capacity_kib <= 0:
            max_capacity_kib = None
        if max_capacity_ex is not None and max_capacity_ex <= 0:
            max_capacity_ex = None
        if max_capacity_kib is not None and max_capacity_ex is not None:
            if max_capacity_kib == max_capacity_ex:
                return max_capacity_kib * 1024
            derived = max_capacity_kib * 1024
            if derived == max_capacity_ex:
                return max_capacity_ex
            return max_capacity_ex
        if max_capacity_ex is not None:
            return max_capacity_ex
        return max_capacity_kib * 1024 if max_capacity_kib is not None else None

    def physical_memory_arrays(self) -> list[PhysicalMemoryArrayResult]:
        results = []
        for node in self._enumerate("Win32_PhysicalMemoryArray"):
            max_capacity_ex = self._optional_positive_int(self._text(node, "MaxCapacityEx"))
            max_capacity_kib = self._optional_positive_int(self._text(node, "MaxCapacity"))
            results.append(PhysicalMemoryArrayResult(
                max_capacity_bytes=self._memory_array_capacity_bytes(max_capacity_kib, max_capacity_ex),
                memory_devices=self._optional_positive_int(self._text(node, "MemoryDevices")),
                location=self._text(node, "Location") or None,
                use=self._optional_positive_int(self._text(node, "Use")),
            ))
        return results

    def hardware_information(self) -> dict[str, list[Any]]:
        """Collect the fixed hardware inventory classes without sensitive IDs."""
        return {
            "computer_system": self.computer_system(),
            "system_product": self.computer_system_product(),
            "baseboard": self.baseboard(),
            "bios": self.bios(),
            "processors": self.hardware_processors(),
            "memory_modules": self.physical_memory(),
            "memory_arrays": self.physical_memory_arrays(),
        }

    def processor(self) -> list[ProcessorResult]:
        results = []
        for node in self._enumerate("Win32_PerfFormattedData_PerfOS_Processor"):
            try:
                results.append(ProcessorResult(self._text(node, "Name"), float(self._text(node, "PercentProcessorTime"))))
            except (TypeError, ValueError):
                raise CIMError("parsing", "Invalid Windows processor data") from None
        return results

    @staticmethod
    def _optional_float(value: str) -> float | None:
        if value in {"", None}:
            return None
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed >= 0 else None

    def processor_performance(self) -> list[ProcessorPerformanceResult]:
        """Return the available per-processor Windows performance counters."""
        results = []
        try:
            nodes = self._enumerate("Win32_PerfFormattedData_PerfOS_Processor")
        except CIMError:
            # Utilization is required; optional advanced fields must not make
            # the CPU module fail on older/limited Windows providers.
            nodes = self._enumerate("Win32_PerfFormattedData_PerfOS_ProcessorRequired")
        for node in nodes:
            results.append(ProcessorPerformanceResult(
                name=self._text(node, "Name"),
                usage_percent=self._optional_float(self._text(node, "PercentProcessorTime")),
                user_percent=self._optional_float(self._text(node, "PercentUserTime")),
                privileged_percent=self._optional_float(self._text(node, "PercentPrivilegedTime")),
                idle_percent=self._optional_float(self._text(node, "PercentIdleTime")),
                interrupts_per_sec=self._optional_float(self._text(node, "InterruptsPerSec")),
                context_switches_per_sec=None,
            ))
        return results

    def system_performance(self) -> list[SystemPerformanceResult]:
        return [SystemPerformanceResult(
            processor_queue_length=self._optional_float(self._text(node, "ProcessorQueueLength")),
            context_switches_per_sec=self._optional_float(self._text(node, "ContextSwitchesPerSec")),
        ) for node in self._enumerate("Win32_PerfFormattedData_PerfOS_System")]

    def memory_performance(self) -> list[MemoryPerformanceResult]:
        return [MemoryPerformanceResult(
            available_mbytes=self._optional_float(self._text(node, "AvailableMBytes")),
            pages_per_sec=self._optional_float(self._counter_text(node, "PagesPersec")),
            page_reads_per_sec=self._optional_float(self._counter_text(node, "PageReadsPersec")),
            page_writes_per_sec=self._optional_float(self._counter_text(node, "PageWritesPersec")),
            page_faults_per_sec=self._optional_float(self._counter_text(node, "PageFaultsPersec")),
            committed_bytes=self._optional_float(self._text(node, "CommittedBytes")),
            commit_limit=self._optional_float(self._text(node, "CommitLimit")),
            cache_bytes=self._optional_float(self._text(node, "CacheBytes")),
            pool_paged_bytes=self._optional_float(self._text(node, "PoolPagedBytes")),
            pool_nonpaged_bytes=self._optional_float(self._text(node, "PoolNonpagedBytes")),
            percent_committed_bytes_in_use=self._optional_float(self._text(node, "PercentCommittedBytesInUse")),
        ) for node in self._enumerate("Win32_PerfFormattedData_PerfOS_Memory")]

    def librehardwaremonitor_sensors(self) -> list[dict[str, str | None]]:
        """Read the optional LibreHardwareMonitor WMI Sensor class."""
        rows = self._enumerate("LibreHardwareMonitor_Sensor", namespace="root/LibreHardwareMonitor")
        return [{field: self._text(node, field) or None for field in (
            "Identifier", "Name", "Value", "SensorType", "HardwareId", "Hardware", "Parent", "Instance", "Min", "Max"
        )} for node in rows]

    @staticmethod
    def _sensor_value(raw: str, *, scale: float = 1.0, offset: float = 0.0) -> float | None:
        try:
            value = float(raw)
            return round(value * scale + offset, 2) if value >= 0 else None
        except (TypeError, ValueError):
            return None

    def native_sensor_discovery(self) -> list[dict[str, object]]:
        collected_at = datetime.now(timezone.utc).isoformat()
        definitions = [
            ("Win32_TemperatureProbe", "temperature", "°C", "root/cimv2", "CurrentReading", 0.1, -273.15),
            ("Win32_Fan", "fan", "rpm", "root/cimv2", "DesiredSpeed", 1.0, 0.0),
            ("Win32_VoltageProbe", "voltage", "V", "root/cimv2", "CurrentReading", 0.001, 0.0),
            ("MSAcpi_ThermalZoneTemperature", "thermal_zone", "°C", "root/wmi", "CurrentTemperature", 0.1, -273.15),
        ]
        sensors: list[dict[str, object]] = []
        for class_name, sensor_type, unit, namespace, value_field, scale, offset in definitions:
            source = f"native_wmi:{namespace}"
            try:
                rows = self._enumerate(class_name, namespace=namespace)
            except CIMError as exc:
                status = "permission_denied" if exc.category in {"permission", "authentication"} else "unavailable"
                sensors.append({"sensor_id": stable_sensor_id(source, sensor_type, class_name), "sensor_name": class_name, "sensor_type": sensor_type, "value": None, "unit": unit, "source": source, "status": status, "error": exc.message, "collected_at": collected_at})
                continue
            if not rows:
                sensors.append({"sensor_id": stable_sensor_id(source, sensor_type, class_name), "sensor_name": class_name, "sensor_type": sensor_type, "value": None, "unit": unit, "source": source, "status": "unsupported", "error": "class_not_returned", "collected_at": collected_at})
                continue
            for index, node in enumerate(rows):
                name = self._first_text(node, "Name", "InstanceName") or class_name
                value = self._sensor_value(self._text(node, value_field), scale=scale, offset=offset)
                display_name = name if len(rows) == 1 else f"{name} [{index}]"
                sensors.append({"sensor_id": stable_sensor_id(source, sensor_type, display_name), "sensor_name": display_name, "sensor_type": sensor_type, "value": value, "unit": unit, "source": source, "status": "ok" if value is not None else "unavailable", "error": None if value is not None else "invalid_reading", "collected_at": collected_at})
        return sensors

    def disks(self) -> list[DiskResult]:
        results = []
        for node in self._enumerate("Win32_LogicalDisk"):
            try:
                results.append(DiskResult(self._text(node, "DeviceID"), int(self._text(node, "Size")), int(self._text(node, "FreeSpace")), self._text(node, "VolumeName")))
            except (TypeError, ValueError):
                raise CIMError("parsing", "Invalid Windows disk data") from None
        return results

    def physical_disks(self) -> list[PhysicalDiskResult]:
        return [PhysicalDiskResult(
            device_id=self._text(node, "DeviceID") or None,
            index=self._optional_int(self._text(node, "Index")),
            model=self._text(node, "Model") or None,
            serial_number=self._text(node, "SerialNumber") or None,
            pnp_device_id=self._text(node, "PNPDeviceID") or None,
            interface_type=self._text(node, "InterfaceType") or None,
            media_type=self._text(node, "MediaType") or None,
            size_bytes=self._optional_positive_int(self._text(node, "Size")),
            firmware_revision=self._text(node, "FirmwareRevision") or None,
            status=self._text(node, "Status") or None,
            partitions=self._optional_positive_int(self._text(node, "Partitions")),
            bytes_per_sector=self._optional_positive_int(self._text(node, "BytesPerSector")),
        ) for node in self._enumerate("Win32_DiskDrive")]

    def disk_partitions(self) -> list[DiskPartitionResult]:
        return [DiskPartitionResult(
            device_id=self._text(node, "DeviceID") or None,
            disk_index=self._optional_int(self._text(node, "DiskIndex")),
            index=self._optional_int(self._text(node, "Index")),
            name=self._text(node, "Name") or None,
            size_bytes=self._optional_positive_int(self._text(node, "Size")),
            starting_offset=self._optional_positive_int(self._text(node, "StartingOffset")),
            partition_type=self._text(node, "Type") or None,
            boot_partition=self._optional_bool(self._text(node, "BootPartition")),
            primary_partition=self._optional_bool(self._text(node, "PrimaryPartition")),
        ) for node in self._enumerate("Win32_DiskPartition")]

    def logical_disk_partition_links(self) -> list[dict[str, str | None]]:
        return [{"antecedent": self._text(node, "Antecedent") or None, "dependent": self._text(node, "Dependent") or None} for node in self._enumerate("Win32_LogicalDiskToPartition")]

    def modern_physical_disks(self) -> list[dict[str, object | None]]:
        rows = self._enumerate("MSFT_PhysicalDisk", namespace="root/Microsoft/Windows/Storage")
        fields = ("FriendlyName", "MediaType", "BusType", "HealthStatus", "OperationalStatus", "Size", "FirmwareVersion", "SerialNumber", "UniqueId", "DeviceId")
        return [{field: self._text(node, field) or None for field in fields} for node in rows]

    def storage_reliability_counters(self) -> list[dict[str, str | None]]:
        """Return raw reliability fields; normalization belongs to the API layer."""
        rows = self._enumerate("MSFT_StorageReliabilityCounter", namespace="root/Microsoft/Windows/Storage")
        fields = ("DeviceId", "Temperature", "TemperatureMax", "Wear", "ReadErrorsTotal", "WriteErrorsTotal", "ReadErrorsCorrected", "WriteErrorsCorrected", "PowerOnHours", "UnsafeShutdownCount")
        return [{field: self._counter_text(node, field) or None for field in fields} for node in rows]

    @staticmethod
    def _association_value(value: str | None, class_name: str) -> str | None:
        if not value:
            return None
        match = re.search(rf'{re.escape(class_name)}\.([^=]+)="([^"]+)"', value, re.IGNORECASE)
        return match.group(2) if match else None

    def disk_inventory(self) -> dict[str, object]:
        started = perf_counter()
        durations: dict[str, float | None] = {"physical_ms": None, "partitions_ms": None, "links_ms": None, "modern_ms": None}
        stages = {"physical": "not_started", "partitions": "not_started", "links": "not_started", "modern": "not_started"}
        failed_stage: str | None = None
        outcome = "failed"
        try:
            for stage, key, collector in (("physical", "physical_ms", self.physical_disks), ("partitions", "partitions_ms", self.disk_partitions), ("links", "links_ms", self.logical_disk_partition_links)):
                stage_started = perf_counter()
                try:
                    if stage == "physical":
                        physical = collector()
                    elif stage == "partitions":
                        partitions = collector()
                    else:
                        links = collector()
                    stages[stage] = "completed"
                except Exception:
                    stages[stage] = "failed"
                    failed_stage = stage
                    raise
                finally:
                    durations[key] = (perf_counter() - stage_started) * 1000

            volumes_by_partition: dict[str, list[str]] = {}
            for link in links:
                partition_id = self._association_value(link.get("antecedent"), "Win32_DiskPartition")
                volume_id = self._association_value(link.get("dependent"), "Win32_LogicalDisk")
                if partition_id and volume_id:
                    volumes_by_partition.setdefault(partition_id, []).append(volume_id)
            partition_rows = []
            for partition in partitions:
                values = {"device_id": partition.device_id, "disk_index": partition.disk_index, "index": partition.index, "name": partition.name, "size_bytes": partition.size_bytes, "starting_offset": partition.starting_offset, "type": partition.partition_type, "boot_partition": partition.boot_partition, "primary_partition": partition.primary_partition, "logical_volumes": volumes_by_partition.get(partition.device_id or "", [])}
                partition_rows.append(values)
            modern_started = perf_counter()
            try:
                modern = self.modern_physical_disks()
                stages["modern"] = "completed"
                modern_status = "ok" if modern else "unsupported"
                modern_error = None if modern else "class_not_returned"
            except CIMError as exc:
                stages["modern"] = "failed"
                modern, modern_status, modern_error = [], "permission_denied" if exc.category in {"permission", "authentication"} else "unavailable", exc.message
            finally:
                durations["modern_ms"] = (perf_counter() - modern_started) * 1000
            outcome = "partial_success" if stages["modern"] == "failed" else "success"
            return {"physical_disks": [disk.__dict__ for disk in physical], "partitions": partition_rows, "modern_physical_disks": modern, "modern_status": modern_status, "modern_error": modern_error}
        finally:
            logger.info("windows_disk_inventory_timing physical_ms=%s partitions_ms=%s links_ms=%s modern_ms=%s total_ms=%.1f failed_stage=%s outcome=%s stage_statuses=%s", *(f"{durations[key]:.1f}" if durations[key] is not None else "not_started" for key in ("physical_ms", "partitions_ms", "links_ms", "modern_ms")), (perf_counter() - started) * 1000, failed_stage or "none", outcome, ",".join(f"{key}:{stages[key]}" for key in ("physical", "partitions", "links", "modern")))

    def disk_performance(self, disk_kind: str) -> list[DiskPerformanceResult]:
        class_name = {
            "logical": "Win32_PerfFormattedData_PerfDisk_LogicalDisk",
            "physical": "Win32_PerfFormattedData_PerfDisk_PhysicalDisk",
        }.get(disk_kind)
        if class_name is None:
            raise ValueError("unsupported disk performance kind")
        results = []
        for node in self._enumerate(class_name):
            number = lambda field: self._optional_float(self._counter_text(node, field))
            seconds_to_ms = lambda field: round(number(field) * 1000, 3) if number(field) is not None else None
            results.append(DiskPerformanceResult(
                instance=self._counter_text(node, "Name") or "",
                read_iops=number("DiskReadsPerSec"),
                write_iops=number("DiskWritesPerSec"),
                total_iops=number("DiskTransfersPerSec"),
                read_bytes_per_sec=number("DiskReadBytesPerSec"),
                write_bytes_per_sec=number("DiskWriteBytesPerSec"),
                total_bytes_per_sec=number("DiskBytesPerSec"),
                read_latency_ms=seconds_to_ms("AvgDiskSecPerRead"),
                write_latency_ms=seconds_to_ms("AvgDiskSecPerWrite"),
                average_latency_ms=seconds_to_ms("AvgDiskSecPerTransfer"),
                average_queue_length=number("AvgDiskQueueLength"),
                current_queue_length=number("CurrentDiskQueueLength"),
                split_io_per_sec=number("SplitIOPerSec"),
                percent_disk_time=number("PercentDiskTime"),
            ))
        return results

    def network_interfaces(self) -> list[NetworkInterfaceResult]:
        """Return normalized adapter data joined by stable Windows identifiers."""
        adapters = self._enumerate("Win32_NetworkAdapter")
        configurations = self._enumerate("Win32_NetworkAdapterConfiguration")
        performance = self._enumerate("Win32_PerfFormattedData_Tcpip_NetworkInterface")

        configuration_by_adapter_index = {
            self._optional_int(self._first_text(node, "Index")): node
            for node in configurations
            if self._optional_int(self._first_text(node, "Index")) is not None
        }
        configuration_by_interface_index = {
            self._optional_int(self._first_text(node, "InterfaceIndex")): node
            for node in configurations
            if self._optional_int(self._first_text(node, "InterfaceIndex")) is not None
        }
        performance_by_identity: dict[str, list[ET.Element]] = {}
        for node in performance:
            identity = self._identity(self._text(node, "Name"))
            if identity:
                performance_by_identity.setdefault(identity, []).append(node)
        unique_performance_by_identity = {
            identity: nodes[0]
            for identity, nodes in performance_by_identity.items()
            if len(nodes) == 1
        }
        results: list[NetworkInterfaceResult] = []
        for node in adapters:
            adapter_index = self._optional_int(self._text(node, "Index"))
            configuration = configuration_by_adapter_index.get(adapter_index)
            # Some providers omit the configuration key. Only use a unique
            # interface-index fallback; never pair records by list position.
            if configuration is None and adapter_index is not None:
                configuration = configuration_by_interface_index.get(adapter_index)
            interface_index = self._optional_int(self._first_text(configuration, "InterfaceIndex"))
            name = self._text(node, "Name") or None
            description = self._text(node, "Description") or None
            perf = next(
                (
                    unique_performance_by_identity.get(self._identity(value))
                    for value in (name, description, self._text(node, "NetConnectionID"))
                    if self._identity(value) in unique_performance_by_identity
                ),
                None,
            )
            ipv4, ipv6 = self._addresses(configuration) if configuration is not None else ((), ())
            status_code = self._optional_int(self._text(node, "NetConnectionStatus"))
            status = "Up" if status_code == 2 else "Down" if status_code == 7 else None
            results.append(
                NetworkInterfaceResult(
                    interface_index=interface_index,
                    name=name,
                    description=description,
                    mac_address=self._first_text(node, "MACAddress") or self._first_text(configuration, "MACAddress") or None,
                    ipv4_addresses=ipv4,
                    ipv6_addresses=ipv6,
                    interface_status=status,
                    link_speed_bps=self._optional_positive_int(self._first_text(node, "Speed"))
                    or self._optional_positive_int(self._first_text(perf, "CurrentBandwidth")),
                    rx_bytes_per_sec=self._optional_positive_int(self._first_text(perf, "BytesReceivedPerSec", "BytesReceivedPersec")),
                    tx_bytes_per_sec=self._optional_positive_int(self._first_text(perf, "BytesSentPerSec", "BytesSentPersec")),
                    adapter_index=adapter_index,
                )
            )
        return results

    def records(self, class_name: str, fields: tuple[str, ...], *, limit: int = 50) -> list[dict[str, str | None]]:
        nodes = self._enumerate(class_name)
        return [{field: self._text(node, field) or None for field in fields} for node in nodes[:limit]]
