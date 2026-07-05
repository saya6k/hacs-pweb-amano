"""The PWEB Amano integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .api import PwebAmanoApiClient
from .const import CONF_CAR_PLATES, DOMAIN
from .coordinator import PwebAmanoCoordinator
from .services import async_register_services

PLATFORMS = [Platform.SENSOR, Platform.CALENDAR, Platform.EVENT, Platform.BUTTON]

type PwebAmanoConfigEntry = ConfigEntry[PwebAmanoCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: PwebAmanoConfigEntry) -> bool:
    """Set up PWEB Amano from a config entry."""
    client = PwebAmanoApiClient(
        entry.data[CONF_HOST], entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD]
    )
    coordinator = PwebAmanoCoordinator(hass, client)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    _async_remove_orphaned_vehicle_devices(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    async_register_services(hass)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


def _async_remove_orphaned_vehicle_devices(
    hass: HomeAssistant, entry: PwebAmanoConfigEntry
) -> None:
    """Drop per-vehicle devices for plates no longer tracked.

    calendar.py/event.py rebuild their entities from entry.options on every
    setup, but HA doesn't automatically prune devices/entities that a
    platform stops producing - a removed or edited plate would otherwise
    leave its old device (and entities) behind as a permanent orphan.
    Removing the device cascades to its entities (EntityRegistry listens for
    device-removal events), so that's all that's needed here.
    """
    # Must match calendar.py/event.py's own blank-filtering exactly, or a
    # blank plate already saved in options (from before _clean_car_plates
    # existed) would be treated as "valid" here while those platforms don't
    # actually create an entity for it - orphaning its device permanently.
    plates = [p for p in (entry.options.get(CONF_CAR_PLATES) or []) if p]
    valid_identifiers = {(DOMAIN, entry.entry_id)} | {
        (DOMAIN, f"{entry.entry_id}_{plate}") for plate in plates
    }

    device_registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
        if not device.identifiers.isdisjoint(valid_identifiers):
            continue
        # Not the site device and not a currently-tracked plate's device.
        device_registry.async_remove_device(device.id)


async def _async_update_listener(hass: HomeAssistant, entry: PwebAmanoConfigEntry) -> None:
    """Reload the entry when options (e.g. tracked car plates) change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: PwebAmanoConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.client.async_close()
    return unloaded
