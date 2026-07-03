"""Event platform for PWEB Amano — vehicle exit events.

Only exit ("출차") events are exposed. The portal has no entry-side ("입차")
log reachable by this account's menus — the only entry-time data we can see
comes bundled with discount registrations, so an "entry" event here would
silently miss any car that never registered a discount. See AGENTS.md.
"""
from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
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
    """Set up the event platform."""
    async_add_entities(
        [PwebAmanoVehicleExitEvent(entry.runtime_data, entry.entry_id)]
    )


class PwebAmanoVehicleExitEvent(CoordinatorEntity[PwebAmanoCoordinator], EventEntity):
    """Fires when a discount-registered vehicle's paid_stat flips to exited."""

    _attr_has_entity_name = True
    _attr_translation_key = "vehicle_exit"
    _attr_event_types = ["exit"]

    def __init__(self, coordinator: PwebAmanoCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_vehicle_exit"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="PWEB Amano",
            manufacturer="Amano Korea",
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        for row in self.coordinator.data.get("new_exits", []):
            self._trigger_event(
                "exit",
                {
                    "car_no": row.get("carno"),
                    "discount_name": row.get("discount_name"),
                    "entry_date": row.get("entry_date"),
                    "registered_at": row.get("reg_date"),
                },
            )
        super()._handle_coordinator_update()
