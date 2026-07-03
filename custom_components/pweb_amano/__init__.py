"""The PWEB Amano integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant

from .api import PwebAmanoApiClient
from .coordinator import PwebAmanoCoordinator
from .services import async_register_services

PLATFORMS = [Platform.SENSOR, Platform.CALENDAR, Platform.EVENT]

type PwebAmanoConfigEntry = ConfigEntry[PwebAmanoCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: PwebAmanoConfigEntry) -> bool:
    """Set up PWEB Amano from a config entry."""
    client = PwebAmanoApiClient(
        entry.data[CONF_HOST], entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD]
    )
    coordinator = PwebAmanoCoordinator(hass, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    async_register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PwebAmanoConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.client.async_close()
    return unloaded
