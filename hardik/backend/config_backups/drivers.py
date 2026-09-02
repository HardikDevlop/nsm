from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ConfigurationDriver(Protocol):
    vendor: str

    def capture(self, device_id: int) -> str:
        """Return live configuration content or raise a driver error."""


@dataclass(frozen=True)
class UnsupportedDriver:
    vendor: str

    def capture(self, device_id: int) -> str:
        raise RuntimeError(f"No configuration driver is registered for vendor {self.vendor}")


DRIVERS: dict[str, ConfigurationDriver] = {}


def register_driver(driver: ConfigurationDriver) -> None:
    DRIVERS[driver.vendor.lower()] = driver


def get_driver(vendor: str | None) -> ConfigurationDriver:
    return DRIVERS.get((vendor or "generic").lower(), UnsupportedDriver(vendor or "generic"))
