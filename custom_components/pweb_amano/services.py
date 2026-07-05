"""Services for PWEB Amano — discount registration (할인등록)."""
from __future__ import annotations

import logging
import string
from datetime import date, timedelta

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, device_registry as dr

from .api import PwebAmanoApiClient
from .const import DOMAIN, SERVICE_LIST_UNREGISTERED_VEHICLES, SERVICE_REGISTER_DISCOUNT
from .exceptions import PwebAmanoError

_LOGGER = logging.getLogger(__name__)

ATTR_DEVICE_ID = "device_id"
ATTR_CAR_NO = "car_no"
ATTR_DISCOUNT_TYPE = "discount_type"
ATTR_MEMO = "memo"
ATTR_ENTRY_DATE = "entry_date"
ATTR_DAYS = "days"

SERVICE_REGISTER_DISCOUNT_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Required(ATTR_CAR_NO): cv.string,
        vol.Required(ATTR_DISCOUNT_TYPE): cv.string,
        vol.Optional(ATTR_MEMO, default=""): cv.string,
        vol.Optional(ATTR_ENTRY_DATE): cv.date,
    }
)
SERVICE_LIST_UNREGISTERED_VEHICLES_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_DEVICE_ID): cv.string,
        vol.Optional(ATTR_DAYS, default=2): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=7)
        ),
    }
)


def _async_resolve_client(hass: HomeAssistant, device_id: str) -> PwebAmanoApiClient:
    """Resolve a service call's device_id to that config entry's API client."""
    device_registry = dr.async_get(hass)
    device = device_registry.async_get(device_id)
    if device is None:
        raise HomeAssistantError(f"unknown device: {device_id}")

    entry_id = next(iter(device.config_entries), None)
    entry = hass.config_entries.async_get_entry(entry_id) if entry_id else None
    if entry is None or entry.domain != DOMAIN:
        raise HomeAssistantError(f"device {device_id} is not a PWEB Amano device")

    return entry.runtime_data.client


def async_register_services(hass: HomeAssistant) -> None:
    """Register the domain's services once, regardless of entry count."""
    if not hass.services.has_service(DOMAIN, SERVICE_REGISTER_DISCOUNT):
        hass.services.async_register(
            DOMAIN,
            SERVICE_REGISTER_DISCOUNT,
            _async_register_discount(hass),
            schema=SERVICE_REGISTER_DISCOUNT_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_LIST_UNREGISTERED_VEHICLES):
        hass.services.async_register(
            DOMAIN,
            SERVICE_LIST_UNREGISTERED_VEHICLES,
            _async_list_unregistered_vehicles(hass),
            schema=SERVICE_LIST_UNREGISTERED_VEHICLES_SCHEMA,
            supports_response=SupportsResponse.ONLY,
        )


def _async_register_discount(hass: HomeAssistant):
    async def _service(call: ServiceCall) -> None:
        client = _async_resolve_client(hass, call.data[ATTR_DEVICE_ID])
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

    return _service


def _async_list_unregistered_vehicles(hass: HomeAssistant):
    async def _service(call: ServiceCall) -> ServiceResponse:
        client = _async_resolve_client(hass, call.data[ATTR_DEVICE_ID])
        today = date.today()
        entry_dates = [
            (today - timedelta(days=offset)).strftime("%Y%m%d")
            for offset in range(call.data[ATTR_DAYS])
        ]

        try:
            # There's no "list every parked car" endpoint (see AGENTS.md) -
            # the search only works by car number, so cast the widest
            # possible net: every plate has at least one of these ten
            # digits somewhere, so searching all of them finds every car.
            await client.async_login()
            found: dict[int, dict] = {}
            for entry_date in entry_dates:
                for digit in string.digits:
                    for row in await client.async_find_parked_entry(digit, entry_date):
                        found[row["id"]] = row
        except PwebAmanoError as err:
            raise HomeAssistantError(str(err)) from err

        vehicles = [
            {
                "car_no": row.get("carNo"),
                "entry_date": row.get("entryDateToString"),
                "minutes_parked": row.get("incar_min"),
            }
            for row in found.values()
            if str(row.get("dscnt_cnt")) == "0"
        ]
        return {"vehicles": vehicles}

    return _service
