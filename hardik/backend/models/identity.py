"""
Device Identity, Capability, OUI Registry and Product Catalog models.

All tables are NEW — no existing tables are altered.
SQLAlchemy create_all() is idempotent; these appear automatically on startup.

Design
------
- device_identity : resolved identity for each device, with per-field
  confidence and source tracking so discovered values are never silently
  overwritten by user overrides.
- device_capabilities : what SNMP modules each device actually supports,
  discovered dynamically by probing the walk result.
- vendor_ouis : database-backed OUI (MAC prefix → vendor) registry.
  Replaces the static in-memory OUI_TABLE in vendor_map.py.
- device_products : product catalog entries for known device models.
  Agnigate and other vendor models are stored here — no Python code
  needs to change when a new model is added.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Index,
    Integer, JSON, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.session import Base


def _now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# device_identity
# ---------------------------------------------------------------------------

class DeviceIdentity(Base):
    """
    Resolved identity snapshot for one device.

    Each field tracks both its current value AND where it came from
    (source) and how confident the system is (confidence 0.0–1.0).

    Override fields allow the user to pin a value without losing the
    discovered value.  The 'value' fields always hold what the system
    should USE (override wins over discovered when set).
    """

    __tablename__ = "device_identity"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"),
        unique=True, index=True,
    )

    # --- Vendor ---
    vendor: Mapped[str | None] = mapped_column(String(120), index=True)
    vendor_source: Mapped[str | None] = mapped_column(
        String(60),
        comment="mac_oui | snmp_sysoid | snmp_descr | entity_mib | user_override | unknown",
    )
    vendor_confidence: Mapped[float | None] = mapped_column(Float)
    vendor_override: Mapped[bool] = mapped_column(Boolean, default=False)

    # --- Hostname ---
    hostname: Mapped[str | None] = mapped_column(String(255))
    hostname_source: Mapped[str | None] = mapped_column(String(60))

    # --- Model ---
    model: Mapped[str | None] = mapped_column(String(160))
    model_source: Mapped[str | None] = mapped_column(String(60))
    model_confidence: Mapped[float | None] = mapped_column(Float)
    model_override: Mapped[bool] = mapped_column(Boolean, default=False)

    # --- Device type (router/switch/firewall/…) ---
    device_type: Mapped[str | None] = mapped_column(String(80), index=True)
    device_type_source: Mapped[str | None] = mapped_column(String(60))
    device_type_confidence: Mapped[float | None] = mapped_column(Float)
    device_type_override: Mapped[bool] = mapped_column(Boolean, default=False)

    # --- Product family ---
    product_family: Mapped[str | None] = mapped_column(String(120))

    # --- Hardware identity ---
    serial_number: Mapped[str | None] = mapped_column(String(160))
    serial_source: Mapped[str | None] = mapped_column(String(60))
    firmware_version: Mapped[str | None] = mapped_column(String(160))
    os_version: Mapped[str | None] = mapped_column(String(160))

    # --- SNMP identity ---
    sys_object_id: Mapped[str | None] = mapped_column(String(255))
    sys_descr: Mapped[str | None] = mapped_column(Text)
    sys_name: Mapped[str | None] = mapped_column(String(255))
    sys_contact: Mapped[str | None] = mapped_column(String(255))
    sys_location: Mapped[str | None] = mapped_column(String(255))

    # --- MAC addresses observed ---
    mac_addresses: Mapped[list] = mapped_column(
        JSON, default=list,
        comment="List of MAC strings seen on this device",
    )

    # --- Roles (list of strings: 'router', 'firewall', 'switch', …) ---
    roles: Mapped[list] = mapped_column(JSON, default=list)

    # --- Overall confidence score 0–1 ---
    identity_confidence: Mapped[float | None] = mapped_column(Float)

    # --- All evidence sources that contributed ---
    identity_sources: Mapped[list] = mapped_column(JSON, default=list)

    # --- Linked product catalog entry (if matched) ---
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("device_products.id", ondelete="SET NULL"), nullable=True
    )

    # --- Timestamps ---
    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_now, onupdate=_now
    )

    # Relationships
    product: Mapped["DeviceProduct | None"] = relationship(
        "DeviceProduct", foreign_keys=[product_id]
    )


# ---------------------------------------------------------------------------
# device_capabilities
# ---------------------------------------------------------------------------

class DeviceCapabilities(Base):
    """
    Which SNMP collectors each device supports, discovered dynamically.

    'supported' means at least one OID in that domain responded during
    the last SNMP walk.  'partial' means some OIDs responded.
    'unsupported' means zero OIDs responded.

    The raw capability map is also stored as JSON for flexible querying.
    """

    __tablename__ = "device_capabilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"),
        unique=True, index=True,
    )

    # Standard capabilities (bool = supported)
    cap_system:      Mapped[bool] = mapped_column(Boolean, default=False)
    cap_cpu:         Mapped[bool] = mapped_column(Boolean, default=False)
    cap_memory:      Mapped[bool] = mapped_column(Boolean, default=False)
    cap_storage:     Mapped[bool] = mapped_column(Boolean, default=False)
    cap_interfaces:  Mapped[bool] = mapped_column(Boolean, default=False)
    cap_environment: Mapped[bool] = mapped_column(Boolean, default=False)
    cap_inventory:   Mapped[bool] = mapped_column(Boolean, default=False)

    # Network capabilities
    cap_vlan:        Mapped[bool] = mapped_column(Boolean, default=False)
    cap_lldp:        Mapped[bool] = mapped_column(Boolean, default=False)
    cap_cdp:         Mapped[bool] = mapped_column(Boolean, default=False)
    cap_routing:     Mapped[bool] = mapped_column(Boolean, default=False)
    cap_arp:         Mapped[bool] = mapped_column(Boolean, default=False)
    cap_mac_table:   Mapped[bool] = mapped_column(Boolean, default=False)

    # Product capabilities
    cap_firewall:    Mapped[bool] = mapped_column(Boolean, default=False)
    cap_vpn:         Mapped[bool] = mapped_column(Boolean, default=False)
    cap_sdwan:       Mapped[bool] = mapped_column(Boolean, default=False)
    cap_wireless:    Mapped[bool] = mapped_column(Boolean, default=False)
    cap_access_point: Mapped[bool] = mapped_column(Boolean, default=False)
    cap_topology:    Mapped[bool] = mapped_column(Boolean, default=False)

    # Full detail map (collector_name → {supported, missing, warnings})
    capability_detail: Mapped[dict] = mapped_column(JSON, default=dict)

    # Timestamps
    discovered_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_now, onupdate=_now
    )

    def to_map(self) -> dict[str, bool]:
        """Return a flat {capability: bool} dict for API responses."""
        return {
            "system":       self.cap_system,
            "cpu":          self.cap_cpu,
            "memory":       self.cap_memory,
            "storage":      self.cap_storage,
            "interfaces":   self.cap_interfaces,
            "environment":  self.cap_environment,
            "inventory":    self.cap_inventory,
            "vlan":         self.cap_vlan,
            "lldp":         self.cap_lldp,
            "cdp":          self.cap_cdp,
            "routing":      self.cap_routing,
            "arp":          self.cap_arp,
            "mac_table":    self.cap_mac_table,
            "firewall":     self.cap_firewall,
            "vpn":          self.cap_vpn,
            "sdwan":        self.cap_sdwan,
            "wireless":     self.cap_wireless,
            "access_point": self.cap_access_point,
            "topology":     self.cap_topology,
        }


# ---------------------------------------------------------------------------
# vendor_ouis  (database-backed OUI registry)
# ---------------------------------------------------------------------------

class VendorOUI(Base):
    """
    OUI (Organizationally Unique Identifier) → manufacturer mapping.

    OUI is the first 3 bytes (6 hex chars) of a MAC address.
    Longer OUIs (24-bit, 28-bit, 36-bit) are supported — longer match wins.

    Source values: 'ieee_public' | 'manual' | 'import'
    """

    __tablename__ = "vendor_ouis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # OUI in normalized lowercase colon-separated form, e.g. "98:a8:78"
    oui: Mapped[str] = mapped_column(String(20), index=True, unique=True)

    # Human-readable manufacturer name
    manufacturer: Mapped[str] = mapped_column(String(200))

    # Short vendor key for internal use (e.g. "agnigate", "cisco")
    vendor_key: Mapped[str | None] = mapped_column(String(80), index=True)

    # Where did this entry come from?
    source: Mapped[str] = mapped_column(String(40), default="manual")

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_now, onupdate=_now
    )

    __table_args__ = (
        Index("ix_vendor_ouis_oui_len", "oui"),
    )


# ---------------------------------------------------------------------------
# device_products  (product catalog)
# ---------------------------------------------------------------------------

class DeviceProduct(Base):
    """
    Known device model catalog entry.

    Agnigate products and other vendor models are stored here.
    Collectors are NOT affected when products are added or changed.

    Matching strategy (in order):
      1. sys_object_id exact or prefix match
      2. model_pattern regex against sysDescr
      3. vendor_key + device_type combination

    Roles is a JSON list: ["firewall", "vpn"] means the product
    functions as both a firewall and a VPN gateway.
    """

    __tablename__ = "device_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Vendor key (matches oid_catalog.py VENDOR_OID_CATALOG keys)
    vendor_key: Mapped[str] = mapped_column(String(80), index=True)

    # Human-readable product name / model
    product_name: Mapped[str] = mapped_column(String(160))
    product_family: Mapped[str | None] = mapped_column(String(120))

    # SNMP identity matching patterns
    sys_object_id_prefix: Mapped[str | None] = mapped_column(String(255), index=True)
    model_pattern: Mapped[str | None] = mapped_column(
        String(255),
        comment="Regex against sysDescr or model string",
    )
    descr_keywords: Mapped[list] = mapped_column(
        JSON, default=list,
        comment="sysDescr substrings that confirm this product",
    )

    # Device classification
    device_type: Mapped[str | None] = mapped_column(String(80))
    roles: Mapped[list] = mapped_column(JSON, default=list)

    # Capabilities this product model always has
    # (overrides dynamic detection when confidence is low)
    default_capabilities: Mapped[dict] = mapped_column(JSON, default=dict)

    # Enabled / disabled
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_now, onupdate=_now
    )

    __table_args__ = (
        UniqueConstraint("vendor_key", "product_name", name="uq_product_vendor_name"),
    )
