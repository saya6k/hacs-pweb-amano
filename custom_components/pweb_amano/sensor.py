"""Sensor platform for PWEB Amano."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import PwebAmanoConfigEntry
from .const import DOMAIN
from .coordinator import PwebAmanoCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PwebAmanoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator = entry.runtime_data
    async_add_entities(
        [
            PwebAmanoLastSyncSensor(coordinator, entry),
            PwebAmanoDiscountBalanceSensor(coordinator, entry),
            PwebAmanoRegistrationStatusSensor(coordinator, entry),
        ]
    )


class PwebAmanoLastSyncSensor(CoordinatorEntity[PwebAmanoCoordinator], SensorEntity):
    """Timestamp of the last successful login + fetch."""

    _attr_has_entity_name = True
    _attr_translation_key = "last_sync"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator: PwebAmanoCoordinator, entry: PwebAmanoConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_last_sync"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Amano Korea",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self):
        return self.coordinator.data.get("last_sync")


class PwebAmanoDiscountBalanceSensor(CoordinatorEntity[PwebAmanoCoordinator], SensorEntity):
    """Remaining prepaid-discount balance (할인권 잔액), in KRW."""

    _attr_has_entity_name = True
    _attr_translation_key = "discount_balance"
    _attr_native_unit_of_measurement = "원"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: PwebAmanoCoordinator, entry: PwebAmanoConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_discount_balance"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Amano Korea",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self):
        return self.coordinator.data.get("balance")


class PwebAmanoRegistrationStatusSensor(
    CoordinatorEntity[PwebAmanoCoordinator], SensorEntity
):
    """Today's discount-registration status (할인 등록현황)."""

    _attr_has_entity_name = True
    _attr_translation_key = "registration_status"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: PwebAmanoCoordinator, entry: PwebAmanoConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_registration_status"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Amano Korea",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self):
        return self.coordinator.data.get("registration_summary", {}).get("used_cnt")

    @property
    def extra_state_attributes(self):
        summary = self.coordinator.data.get("registration_summary", {})
        return {
            "free_registration_count": summary.get("used_basic"),
            "paid_registration_count": summary.get("used_charge"),
            "total_discount_amount": summary.get("discount_price"),
            "available_discount_types": self.coordinator.data.get("discount_types", {}),
        }
