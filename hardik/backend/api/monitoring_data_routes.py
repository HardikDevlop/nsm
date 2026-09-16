"""
Monitoring Data API - Returns stored monitoring data from database (no live polling)
This API reads from latest_* tables that are populated by the background polling scheduler.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Body
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.services.device_health import derive_device_health
from backend.models import Device
from backend.models.snmp import (
    LatestCPU, LatestMemory, LatestStorage, LatestInterface, LatestEnvironment,
    MonitoringConfig, CPUStatistic, MemoryStatistic, StorageStatistic, InterfaceStatistic
)
from backend.models.identity import DeviceCapabilities

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["Monitoring Data"])


class MonitoringDataRequest(BaseModel):
    """Request body for getting monitoring data."""
    device_id: int
    modules: list[str] = ["cpu", "memory", "storage", "interfaces"]  # Default modules
    include_history: bool = False  # Whether to include historical data
    history_hours: int = 1  # Hours of history to include


def _get_device_or_404(device_id: int, db: Session) -> Device:
    device = db.query(Device).filter(
        Device.id == device_id,
        Device.deleted_at.is_(None),
    ).first()
    if not device:
        raise HTTPException(status_code=404, detail=f"Device {device_id} not found")
    return device


@router.post("/monitoring/data")
def get_monitoring_data(
    request: MonitoringDataRequest = Body(...),
    db: Session = Depends(get_db),
    # _: Any = Depends(require_permission("devices:read")),  # Temporarily disabled for testing
) -> dict[str, Any]:
    """
    Get latest monitoring data for a device from database (NO live polling).
    
    This endpoint reads from the latest_* tables that are populated by 
    the background monitoring scheduler.
    
    Request Body:
    {
        "device_id": 123,
        "modules": ["cpu", "memory", "storage", "interfaces", "environment"],
        "include_history": false,
        "history_hours": 1
    }
    
    Response includes:
    - Latest data for each requested module
    - Monitoring configuration (interval, status)
    - Capabilities (which modules are supported)
    - Optional: Historical data (if include_history=true)
    """
    device = _get_device_or_404(request.device_id, db)
    
    result = {
        "device_id": request.device_id,
        "ip_address": device.ip_address,
        "hostname": device.hostname,
        "status": device.status,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "health": derive_device_health(db, device),
        "modules": {},
        "monitoring_configs": {},
        "capabilities": {},
    }
    
    # Get device capabilities
    dc = db.query(DeviceCapabilities).filter(
        DeviceCapabilities.device_id == request.device_id
    ).first()
    
    if dc:
        result["capabilities"] = dc.to_map()
    capability_detail = dc.capability_detail if dc and isinstance(dc.capability_detail, dict) else {}
    
    # Get monitoring configurations
    configs = db.query(MonitoringConfig).filter(
        MonitoringConfig.device_id == request.device_id
    ).all()
    
    for config in configs:
        result["monitoring_configs"][config.module_name] = {
            "enabled": config.enabled,
            "interval_seconds": config.interval_seconds,
            "status": config.status,
            "last_poll_at": config.last_poll_at.isoformat() if config.last_poll_at else None,
            "next_poll_at": config.next_poll_at.isoformat() if config.next_poll_at else None,
            "error_message": config.error_message,
        }
    
    # Fetch latest data for each requested module
    if "cpu" in request.modules:
        cpu = db.query(LatestCPU).filter(LatestCPU.device_id == request.device_id).first()
        cpu_data = None
        if cpu:
            cpu_data = {
                "utilization_percent": cpu.utilization_percent,
                "per_core": cpu.per_core or {},
                "load_avg": cpu.load_avg or {},
                "polled_at": cpu.polled_at.isoformat() if cpu.polled_at else None,
            }
        
        result["modules"]["cpu"] = {
            "supported": result["capabilities"].get("cpu", False),
            "data": cpu_data,
            "history": [],
        }
        
        # Add history if requested
        if request.include_history and cpu_data:
            since = datetime.utcnow() - timedelta(hours=request.history_hours)
            history = db.query(CPUStatistic).filter(
                CPUStatistic.device_id == request.device_id,
                CPUStatistic.created_at >= since
            ).order_by(CPUStatistic.created_at.asc()).all()
            
            result["modules"]["cpu"]["history"] = [
                {
                    "timestamp": h.created_at.isoformat(),
                    "utilization_percent": h.utilization_percent,
                }
                for h in history
            ]
    
    if "memory" in request.modules:
        mem = db.query(LatestMemory).filter(LatestMemory.device_id == request.device_id).first()
        mem_data = None
        if mem:
            mem_data = {
                "total_bytes": mem.total_bytes,
                "used_bytes": mem.used_bytes,
                "free_bytes": mem.free_bytes,
                "cached_bytes": mem.cached_bytes,
                "buffer_bytes": mem.buffer_bytes,
                "swap_total": mem.swap_total,
                "swap_free": mem.swap_free,
                "utilization_percent": mem.utilization_percent,
                "polled_at": mem.polled_at.isoformat() if mem.polled_at else None,
            }
        
        result["modules"]["memory"] = {
            "supported": result["capabilities"].get("memory", False),
            "data": mem_data,
            "history": [],
        }
        
        # Add history if requested
        if request.include_history and mem_data:
            since = datetime.utcnow() - timedelta(hours=request.history_hours)
            history = db.query(MemoryStatistic).filter(
                MemoryStatistic.device_id == request.device_id,
                MemoryStatistic.created_at >= since
            ).order_by(MemoryStatistic.created_at.asc()).all()
            
            result["modules"]["memory"]["history"] = [
                {
                    "timestamp": h.created_at.isoformat(),
                    "utilization_percent": h.utilization_percent,
                    "used_bytes": h.used_bytes,
                    "total_bytes": h.total_bytes,
                }
                for h in history
            ]
    
    if "storage" in request.modules:
        storage_items = db.query(LatestStorage).filter(
            LatestStorage.device_id == request.device_id
        ).all()
        
        storage_data = None
        if storage_items:
            storage_data = {
                "volumes": [
                    {
                        "volume_id": s.volume_id,
                        "mount_name": s.mount_name,
                        "total_bytes": s.total_bytes,
                        "used_bytes": s.used_bytes,
                        "free_bytes": s.free_bytes,
                        "utilization_percent": s.utilization_percent,
                        "type_label": s.type_label,
                        "polled_at": s.polled_at.isoformat() if s.polled_at else None,
                    }
                    for s in storage_items
                ]
            }
        
        result["modules"]["storage"] = {
            "supported": result["capabilities"].get("storage", False),
            "data": storage_data,
            "history": [],
        }
        
        # Add history if requested
        if request.include_history and storage_data:
            since = datetime.utcnow() - timedelta(hours=request.history_hours)
            history = db.query(StorageStatistic).filter(
                StorageStatistic.device_id == request.device_id,
                StorageStatistic.created_at >= since
            ).order_by(StorageStatistic.created_at.asc()).all()
            
            result["modules"]["storage"]["history"] = [
                {
                    "timestamp": h.created_at.isoformat(),
                    "mount_name": h.mount_name,
                    "utilization_percent": h.utilization_percent,
                    "used_bytes": h.used_bytes,
                    "total_bytes": h.total_bytes,
                }
                for h in history
            ]
    
    if "interfaces" in request.modules:
        interfaces = db.query(LatestInterface).filter(
            LatestInterface.device_id == request.device_id
        ).all()
        
        interface_data = None
        
        if interfaces:
            interface_data = {
                "interfaces": [
                    {
                        "if_index": i.if_index,
                        "name": i.name,
                        "oper_status": i.oper_status,
                        "admin_status": i.admin_status,
                        "speed_bps": i.speed_bps,
                        "rx_mbps": i.rx_mbps,
                        "tx_mbps": i.tx_mbps,
                        "rx_octets": i.rx_octets,
                        "tx_octets": i.tx_octets,
                        "rx_packets": i.rx_packets,
                        "tx_packets": i.tx_packets,
                        "errors": i.errors,
                        "discards": i.discards,
                        "utilization_percent": i.utilization_percent,
                        "polled_at": i.polled_at.isoformat() if i.polled_at else None,
                    }
                    for i in interfaces
                ]
            }
        
        result["modules"]["interfaces"] = {
            "supported": result["capabilities"].get("interfaces", False),
            "data": interface_data,
            "history": [],
        }
        
        # Add history if requested (for first interface only to keep response size manageable)
        if request.include_history and interface_data and interfaces:
            since = datetime.utcnow() - timedelta(hours=request.history_hours)
            first_interface = interfaces[0]
            history = db.query(InterfaceStatistic).filter(
                InterfaceStatistic.device_id == request.device_id,
                InterfaceStatistic.interface_id == first_interface.interface_id,
                InterfaceStatistic.created_at >= since
            ).order_by(InterfaceStatistic.created_at.asc()).all()
            
            result["modules"]["interfaces"]["history"] = [
                {
                    "timestamp": h.created_at.isoformat(),
                    "rx_mbps": h.rx_mbps,
                    "tx_mbps": h.tx_mbps,
                    "utilization_percent": h.utilization_percent,
                    "error_rate": h.error_rate,
                }
                for h in history
            ]
    
    # Add VLAN module
    if "vlan" in request.modules:
        result["modules"]["vlan"] = {
            "supported": result["capabilities"].get("vlan", False),
            "data": None,
            "history": [],
        }
    
    # Add LLDP module
    if "lldp" in request.modules:
        result["modules"]["lldp"] = {
            "supported": result["capabilities"].get("lldp", False),
            "data": None,
            "history": [],
        }
    
    # Add Routing module
    if "routing" in request.modules:
        result["modules"]["routing"] = {
            "supported": result["capabilities"].get("routing", False),
            "data": None,
            "history": [],
        }
    
    # Add ARP module
    if "arp" in request.modules:
        result["modules"]["arp"] = {
            "supported": result["capabilities"].get("arp", False),
            "data": None,
            "history": [],
        }
    
    # Add MAC Table module
    if "mac_table" in request.modules:
        result["modules"]["mac_table"] = {
            "supported": result["capabilities"].get("mac_table", False),
            "data": None,
            "history": [],
        }
    
    # Add Inventory module
    if "inventory" in request.modules:
        result["modules"]["inventory"] = {
            "supported": result["capabilities"].get("inventory", False),
            "data": None,
            "history": [],
        }
    
    # Add Topology module
    if "topology" in request.modules:
        result["modules"]["topology"] = {
            "supported": result["capabilities"].get("topology", False),
            "data": None,
            "history": [],
        }
    
    if "environment" in request.modules:
        sensors = db.query(LatestEnvironment).filter(
            LatestEnvironment.device_id == request.device_id
        ).all()
        
        env_data = None
        if sensors:
            env_data = {
                "sensors": [
                    {
                        "sensor_id": e.sensor_id,
                        "sensor_name": e.sensor_name,
                        "sensor_type": e.sensor_type,
                        "value": e.value,
                        "unit": e.unit,
                        "status": e.status,
                        "polled_at": e.polled_at.isoformat() if e.polled_at else None,
                    }
                    for e in sensors
                ]
            }
        
        result["modules"]["environment"] = {
            "supported": result["capabilities"].get("environment", False),
            "data": env_data,
            "history": [],
        }

    for module in request.modules:
        cached = capability_detail.get(module) if isinstance(capability_detail.get(module), dict) else None
        if not cached:
            continue
        current = result["modules"].get(module)
        cached_supported = cached.get("supported") is True
        cached_data = cached.get("data")
        if current is None:
            result["modules"][module] = {
                "supported": cached_supported,
                "data": cached_data if cached_supported else None,
                "history": [],
                "timestamp": cached.get("timestamp"),
                "reason": cached.get("reason"),
                "missing": cached.get("missing", []),
                "warnings": cached.get("warnings", []),
            }
            result["capabilities"][module] = cached_supported
            continue
        if current.get("data") is None and cached_supported:
            current["data"] = cached_data
        current["supported"] = current.get("supported") or cached_supported
        current["timestamp"] = current.get("timestamp") or cached.get("timestamp")
        current["reason"] = current.get("reason") or cached.get("reason")
        current["missing"] = current.get("missing") or cached.get("missing", [])
        current["warnings"] = current.get("warnings") or cached.get("warnings", [])
    
    return result


@router.get("/monitoring/data/{device_id}")
def get_monitoring_data_simple(
    device_id: int,
    modules: str = "cpu,memory,storage,interfaces",
    include_history: bool = False,
    history_hours: int = 1,
    db: Session = Depends(get_db),
    # _: Any = Depends(require_permission("devices:read")),  # Temporarily disabled for testing
) -> dict[str, Any]:
    """
    GET version of monitoring data API (for simple testing).
    
    Example:
    GET /api/v1/monitoring/data/123?modules=cpu,memory&include_history=true&history_hours=2
    """
    module_list = [m.strip() for m in modules.split(",") if m.strip()]
    
    request = MonitoringDataRequest(
        device_id=device_id,
        modules=module_list,
        include_history=include_history,
        history_hours=history_hours,
    )
    
    return get_monitoring_data(request, db)
