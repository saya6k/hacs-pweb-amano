"""Calendar platform for PWEB Amano — parking history (주차 내역).

HA calendars are queried on demand for arbitrary date ranges (e.g. when a
dashboard renders a month view), so this doesn't ride along with the normal
poll: async_get_events calls the coordinator directly, which still owns all
network I/O per AGENTS.md.

Only tracks the car plates configured via the options flow (Configure) -
this account can register discounts for any car (its own, a visitor's, a
family member's), so a discount-registration record alone doesn't mean "my
car"; the tracked-plate list is what narrows it down. Events span the
vehicle's actual parking duration (entry_date to dtOutDate), not just the
discount registration's timestamp.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from . import PwebAmanoConfigEntry
from .const import CONF_CAR_PLATES, DOMAIN
from .coordinator import PwebAmanoCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PwebAmanoConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the calendar platform."""
    async_add_entities(
        [PwebAmanoParkingHistoryCalendar(entry.runtime_data, entry)]
    )


def _parse_amano_datetime(value: str | None) -> datetime | None:
    """Parse a yyyyMMddHHmmss (or bare yyyyMMdd) timestamp from the portal.

    The portal has no timezone concept of its own - these are wall-clock
    times in whatever timezone the site operates in (assumed to match HA's
    configured timezone). CalendarEvent requires aware datetimes, so localize
    rather than leaving this naive - see dt_util.as_local: a naive value gets
    HA's local tzinfo attached as-is, with no numeric shift.
    """
    value = (value or "").strip()
    if not value:
        return None
    if len(value) >= 14:
        parsed = datetime.strptime(value[:14], "%Y%m%d%H%M%S")
    else:
        parsed = datetime.strptime(value[:8], "%Y%m%d")
    return dt_util.as_local(parsed)


def _row_to_event(row: dict) -> CalendarEvent:
    start = _parse_amano_datetime(row.get("entry_date"))
    end = _parse_amano_datetime(row.get("dtOutDate"))
    if start is None:
        start = _parse_amano_datetime(row.get("reg_date"))
    if end is None or end <= start:
        end = start + timedelta(minutes=1)
    memo = row.get("memo") or "-"
    return CalendarEvent(
        start=start,
        end=end,
        summary=f"{row.get('carno', '')} {row.get('discount_name', '')}".strip(),
        description=f"할인 등록: {row.get('reg_date', '')} / 비고: {memo}",
    )


class PwebAmanoParkingHistoryCalendar(
    CoordinatorEntity[PwebAmanoCoordinator], CalendarEntity
):
    """Parking history (입차~출차) of the configured car plates."""

    _attr_has_entity_name = True
    _attr_translation_key = "parking_history"

    def __init__(self, coordinator: PwebAmanoCoordinator, entry: PwebAmanoConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_parking_history"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Amano Korea",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def event(self) -> CalendarEvent | None:
        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        plates = self._entry.options.get(CONF_CAR_PLATES) or []
        if not plates:
            return []
        rows = await self.coordinator.async_get_discount_events(
            start_date.strftime("%Y%m%d"), end_date.strftime("%Y%m%d")
        )
        return [
            _row_to_event(row) for row in rows if row.get("carno") in plates
        ]
