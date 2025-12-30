"""The Invoxia (unofficial) integration."""
from __future__ import annotations

import asyncio
from typing import Any

# Import gps_tracker lazily inside async_setup_entry to avoid import-time crashes
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ENTITIES, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .const import CLIENT, DOMAIN, LOGGER, TRACKERS
from .helpers import get_invoxia_client

PLATFORMS: list[Platform] = [Platform.DEVICE_TRACKER]


def _import_gps_tracker():
    """Import gps_tracker module (blocking operation run in thread)."""
    import gps_tracker  # type: ignore
    return gps_tracker


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up GPS Tracker from a config entry."""
    hass.data.setdefault(DOMAIN, {}).setdefault(entry.entry_id, {})

    # Import the gps_tracker library lazily and handle import-time failures.
    # Use to_thread to avoid blocking the event loop during import
    try:
        gps_tracker = await asyncio.to_thread(_import_gps_tracker)
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

    # Fetch trackers and validate they can be accessed before forwarding setup
    try:
        trackers = await client.get_trackers()
    except gps_tracker.client.exceptions.GpsTrackerException as err:
        raise ConfigEntryNotReady(f"Failed to get trackers: {err}") from err
    
    if not trackers:
        LOGGER.warning("No trackers found for account %s", entry.data[CONF_USERNAME])
        # Still proceed with setup even if no trackers are found
        # User might add trackers later
    else:
        # Test that we can fetch data for all trackers before forwarding
        # This validates the API is working properly and provides visibility
        # into which trackers are accessible
        found_working_tracker = False
        for test_tracker in trackers:
            try:
                await client.get_locations(test_tracker, max_count=1)
                LOGGER.debug("Successfully validated API access with tracker %s", test_tracker.id)
                found_working_tracker = True
                # Continue validating remaining trackers to log all failures
            except gps_tracker.client.exceptions.GpsTrackerException as err:
                LOGGER.warning("Failed to validate tracker %s: %s", test_tracker.id, err)
                continue

        if not found_working_tracker:
            # None of the trackers validated successfully during setup
            # Treat this as a transient setup failure so Home Assistant retries the entry
            raise ConfigEntryNotReady(
                f"Could not validate any tracker during setup for account {entry.data[CONF_USERNAME]}"
            )

    # Store all trackers in hass.data (including those that failed validation)
    # This is intentional - coordinators will automatically retry for failed trackers
    # Also prevents device_tracker.py from needing to call get_trackers() again
    hass.data[DOMAIN][entry.entry_id][CLIENT] = client
    hass.data[DOMAIN][entry.entry_id][CONF_ENTITIES] = []
    hass.data[DOMAIN][entry.entry_id][TRACKERS] = trackers

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
