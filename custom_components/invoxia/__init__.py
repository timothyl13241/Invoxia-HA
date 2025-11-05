"""The Invoxia (unofficial) integration."""
from __future__ import annotations

from typing import Any

# Import gps_tracker lazily inside async_setup_entry to avoid import-time crashes
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ENTITIES, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .const import CLIENT, DOMAIN
from .helpers import get_invoxia_client

PLATFORMS: list[Platform] = [Platform.DEVICE_TRACKER]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up GPS Tracker from a config entry."""
    hass.data.setdefault(DOMAIN, {}).setdefault(entry.entry_id, {})

    # Import the gps_tracker library lazily and handle import-time failures.
    try:
        import gps_tracker  # type: ignore
    except Exception as err:
        # Import error or metadata KeyError in gps_tracker — fail setup cleanly so HA can retry
        raise ConfigEntryNotReady(f"Failed to import gps_tracker library: {err}") from err

    config = gps_tracker.Config(  # type: ignore[call-arg]
        password=entry.data[CONF_PASSWORD],
        username=entry.data[CONF_USERNAME],
    )

    client = get_invoxia_client(hass, config)

    try:
        await client.get_devices()
    except gps_tracker.client.exceptions.UnauthorizedQuery as err:
        raise ConfigEntryAuthFailed(err) from err
    except gps_tracker.client.exceptions.GpsTrackerException as err:
        raise ConfigEntryNotReady(err) from err

    hass.data[DOMAIN][entry.entry_id][CLIENT] = client
    hass.data[DOMAIN][entry.entry_id][CONF_ENTITIES] = []

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        client = hass.data[DOMAIN].get(entry.entry_id, {}).get(CLIENT)
        if client is not None and hasattr(client, "close"):
            await client.close()
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok
