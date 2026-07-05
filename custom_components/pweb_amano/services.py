"""Services for PWEB Amano — discount registration (할인등록)."""
from __future__ import annotations

import logging
from datetime import date, timedelta

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, device_registry as dr

from .const import DOMAIN, SERVICE_REGISTER_DISCOUNT
from .exceptions import PwebAmanoError

_LOGGER = logging.getLogger(__name__)

ATTR_DEVICE_ID = "device_id"
ATTR_CAR_NO = "car_no"
ATTR_DISCOUNT_TYPE = "discount_type"
ATTR_MEMO = "memo"
ATTR_ENTRY_DATE = "entry_date"

SERVICE_REGISTER_DISCOUNT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required(ATTR_CAR_NO): cv.string,
        vol.Required(ATTR_DISCOUNT_TYPE): cv.string,
        vol.Optional(ATTR_MEMO, default=""): cv.string,
        vol.Optional(ATTR_ENTRY_DATE): cv.date,
    }
)


def async_register_services(hass: HomeAssistant) -> None:
    """Register the domain's services once, regardless of entry count."""
    if hass.services.has_service(DOMAIN, SERVICE_REGISTER_DISCOUNT):
        return

    async def _async_register_discount(call: ServiceCall) -> None:
        device_registry = dr.async_get(hass)
        device = device_registry.async_get(call.data[ATTR_DEVICE_ID])
        if device is None:
            raise HomeAssistantError(f"unknown device: {call.data[ATTR_DEVICE_ID]}")

        entry_id = next(iter(device.config_entries), None)
        entry = hass.config_entries.async_get_entry(entry_id) if entry_id else None
        if entry is None or entry.domain != DOMAIN:
            raise HomeAssistantError(
                f"device {call.data[ATTR_DEVICE_ID]} is not a PWEB Amano device"
            )

        client = entry.runtime_data.client
        car_no = call.data[ATTR_CAR_NO]

        # Visitor cars are the common case, and the caller usually doesn't
        # know (or care) whether the portal logged the entry as yesterday or
        # today (e.g. an overnight visitor) - the portal has no ranged
        # search, so search both days and take the first match, unless the
        # caller pinned an explicit entry_date.
        if call.data.get(ATTR_ENTRY_DATE):
            candidate_dates = [call.data[ATTR_ENTRY_DATE]]
        else:
            today = date.today()
            candidate_dates = [today - timedelta(days=1), today]

        try:
            parked = []
            for candidate_date in candidate_dates:
                parked = await client.async_find_parked_entry(
                    car_no, candidate_date.strftime("%Y%m%d")
                )
                if parked:
                    break

            if not parked:
                searched = ", ".join(d.strftime("%Y%m%d") for d in candidate_dates)
                raise HomeAssistantError(
                    f"차량 '{car_no}'을(를) 주차장에서 찾을 수 없습니다 "
                    f"(entry_date={searched})"
                )
            await client.async_register_discount(
                pe_id=parked[0]["id"],
                car_no=car_no,
                discount_type=call.data[ATTR_DISCOUNT_TYPE],
                memo=call.data.get(ATTR_MEMO, ""),
            )
        except PwebAmanoError as err:
            raise HomeAssistantError(str(err)) from err

    hass.services.async_register(
        DOMAIN,
        SERVICE_REGISTER_DISCOUNT,
        _async_register_discount,
        schema=SERVICE_REGISTER_DISCOUNT_SCHEMA,
    )
