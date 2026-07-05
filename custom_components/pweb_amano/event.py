"""Event platform for PWEB Amano — vehicle entry/exit for tracked car plates.

Only tracks the car plates configured via the options flow (see
calendar.py's docstring for why: this account can register discounts for
any car, not just "its own"). "Entry" fires the first time we notice a
registration for a tracked plate - not a live detection, since the portal
has no dedicated in/out log and a discount is often registered well after
the car actually parked (see coordinator.py). "Exit" fires when paid_stat
flips to exited for a plate already being tracked, which is a genuine
real-time signal for a car whose discount was registered while still
parked. See AGENTS.md.
"""
from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import PwebAmanoConfigEntry
from .const import CONF_CAR_PLATES, DOMAIN
from .coordinator import PwebAmanoCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PwebAmanoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the event platform."""
    async_add_entities(
        [PwebAmanoVehicleParkingEvent(entry.runtime_data, entry)]
    )


class PwebAmanoVehicleParkingEvent(CoordinatorEntity[PwebAmanoCoordinator], EventEntity):
    """Fires "entry"/"exit" for the configured car plates."""

    _attr_has_entity_name = True
    _attr_translation_key = "vehicle_parking"
    _attr_event_types = ["entry", "exit"]

    def __init__(self, coordinator: PwebAmanoCoordinator, entry: PwebAmanoConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_vehicle_parking"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Amano Korea",
            entry_type=DeviceEntryType.SERVICE,
        )

    def _tracked(self, rows: list[dict]) -> list[dict]:
        plates = self._entry.options.get(CONF_CAR_PLATES) or []
        return [row for row in rows if row.get("carno") in plates]

    @callback
    def _handle_coordinator_update(self) -> None:
        # EventEntity only keeps the *last* _trigger_event call's data until
        # state is written - call async_write_ha_state() after each one, or
        # multiple events in the same poll (e.g. entry+exit firing together
        # for a newly-discovered registration) silently lose all but the
        # final one.
        for event_type, key in (("entry", "new_entries"), ("exit", "new_exits")):
            for row in self._tracked(self.coordinator.data.get(key, [])):
                self._trigger_event(
                    event_type,
                    {
                        "car_no": row.get("carno"),
                        "discount_name": row.get("discount_name"),
                        "entry_date": row.get("entry_date"),
                        "registered_at": row.get("reg_date"),
                    },
                )
                self.async_write_ha_state()
        super()._handle_coordinator_update()
