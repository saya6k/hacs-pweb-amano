"""Config flow for PWEB Amano.

Four steps: (1) the numeric iLotArea from the portal's hostname, which we
use to fetch and show the site name off the unauthenticated /login page so
the user can confirm they've got the right building, then (2) that
confirmation, then (3) ID/password, then (4) optionally the car plates to
track (same field the options flow below manages - skippable here and
addable/editable any time after via Configure).
"""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .api import PwebAmanoApiClient, async_fetch_site_name, normalize_base_url
from .const import CONF_CAR_PLATES, DOMAIN
from .exceptions import PwebAmanoAuthError, PwebAmanoConnectionError

_LOGGER = logging.getLogger(__name__)

CONF_ILOT_AREA = "ilot_area"

STEP_ILOT_AREA_DATA_SCHEMA = vol.Schema({vol.Required(CONF_ILOT_AREA): str})
STEP_CREDENTIALS_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)
STEP_OPTIONS_DATA_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_CAR_PLATES): selector.TextSelector(
            selector.TextSelectorConfig(multiple=True)
        ),
    }
)


def _clean_car_plates(user_input: dict[str, Any]) -> dict[str, Any]:
    """Strip/drop blank entries - the multi-text selector can submit empty rows.

    An empty-string plate would otherwise get its own (unnamed) device, since
    calendar.py/event.py create one device per entry in this list.
    """
    plates = user_input.get(CONF_CAR_PLATES) or []
    cleaned = [plate.strip() for plate in plates if plate.strip()]
    return {**user_input, CONF_CAR_PLATES: cleaned}


class PwebAmanoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for PWEB Amano."""

    VERSION = 1

    @staticmethod
    @config_entries.callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> PwebAmanoOptionsFlow:
        """Get the options flow for this handler."""
        return PwebAmanoOptionsFlow()

    def __init__(self) -> None:
        self._host: str | None = None
        self._site_name: str | None = None
        self._data: dict[str, Any] | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: collect the iLotArea and look up the site name for it."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = normalize_base_url(f"a{user_input[CONF_ILOT_AREA].strip()}.pweb.kr")
            try:
                self._site_name = await async_fetch_site_name(host)
            except PwebAmanoConnectionError as err:
                _LOGGER.warning("Could not fetch site name from %s: %s", host, err)
                errors["base"] = "cannot_connect"
            else:
                self._host = host
                return await self.async_step_confirm()

        return self.async_show_form(
            step_id="user", data_schema=STEP_ILOT_AREA_DATA_SCHEMA, errors=errors
        )

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2: show the resolved site name for the user to confirm."""
        if user_input is not None:
            return await self.async_step_credentials()

        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders={"site_name": self._site_name},
        )

    async def async_step_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 3: collect ID/password and log in."""
        errors: dict[str, str] = {}

        if user_input is not None:
            await self.async_set_unique_id(
                f"{self._host}:{user_input[CONF_USERNAME]}"
            )
            self._abort_if_unique_id_configured()

            client = PwebAmanoApiClient(
                self._host, user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
            )
            try:
                await client.async_login()
            except PwebAmanoAuthError as err:
                _LOGGER.debug("Login rejected for %s: %s", self._host, err)
                errors["base"] = "invalid_auth"
            except PwebAmanoConnectionError as err:
                _LOGGER.warning("Could not reach %s: %s", self._host, err)
                errors["base"] = "cannot_connect"
            else:
                self._data = {
                    CONF_HOST: self._host,
                    CONF_USERNAME: user_input[CONF_USERNAME],
                    CONF_PASSWORD: user_input[CONF_PASSWORD],
                }
                return await self.async_step_car_plates()
            finally:
                await client.async_close()

        return self.async_show_form(
            step_id="credentials",
            data_schema=STEP_CREDENTIALS_DATA_SCHEMA,
            errors=errors,
            description_placeholders={"site_name": self._site_name},
        )

    async def async_step_car_plates(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 4: optionally list the car plates to track (skippable)."""
        if user_input is not None:
            return self.async_create_entry(
                title=self._site_name or self._host,
                data=self._data,
                options=_clean_car_plates(user_input),
            )

        return self.async_show_form(
            step_id="car_plates", data_schema=STEP_OPTIONS_DATA_SCHEMA
        )


class PwebAmanoOptionsFlow(config_entries.OptionsFlow):
    """Manage the car plates the parking-history calendar tracks."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Single step: edit the tracked car-plate list."""
        if user_input is not None:
            return self.async_create_entry(data=_clean_car_plates(user_input))

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                STEP_OPTIONS_DATA_SCHEMA, self.config_entry.options
            ),
        )
