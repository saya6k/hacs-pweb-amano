"""Calendar platform for PWEB Amano — discount history (할인 내역).

HA calendars are queried on demand for arbitrary date ranges (e.g. when a
dashboard renders a month view), so this doesn't ride along with the normal
poll: async_get_events calls the coordinator directly, which still owns all
network I/O per AGENTS.md.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
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
    """Set up the calendar platform."""
    async_add_entities(
        [PwebAmanoDiscountHistoryCalendar(entry.runtime_data, entry.entry_id)]
    )


def _parse_amano_datetime(value: str | None) -> datetime:
    """Parse a yyyyMMddHHmmss (or bare yyyyMMdd) timestamp from the portal."""
    value = (value or "").strip()
    if len(value) >= 14:
        return datetime.strptime(value[:14], "%Y%m%d%H%M%S")
    return datetime.strptime(value[:8], "%Y%m%d")


def _row_to_event(row: dict) -> CalendarEvent:
    start = _parse_amano_datetime(row.get("reg_date") or row.get("entry_date"))
    memo = row.get("memo") or "-"
    return CalendarEvent(
        start=start,
        end=start + timedelta(minutes=1),
        summary=f"{row.get('carno', '')} {row.get('discount_name', '')}".strip(),
        description=f"입차: {row.get('entry_date', '')} / 비고: {memo}",
    )


class PwebAmanoDiscountHistoryCalendar(
    CoordinatorEntity[PwebAmanoCoordinator], CalendarEntity
):
    """History log of registered discounts — there is no "upcoming" event."""

    _attr_has_entity_name = True
    _attr_translation_key = "discount_history"

    def __init__(self, coordinator: PwebAmanoCoordinator, entry_id: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry_id}_discount_history"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="PWEB Amano",
            manufacturer="Amano Korea",
        )

    @property
    def event(self) -> CalendarEvent | None:
        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        rows = await self.coordinator.async_get_discount_events(
            start_date.strftime("%Y%m%d"), end_date.strftime("%Y%m%d")
        )
        return [_row_to_event(row) for row in rows]
