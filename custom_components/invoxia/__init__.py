"""The Invoxia (unofficial) integration."""
from __future__ import annotations

import asyncio
from typing import Any

# Import gps_tracker lazily inside async_setup_entry to avoid import-time crashes
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ENTITIES, CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .const import CLIENT, COORDINATORS, DOMAIN, LOGGER, TRACKERS
from .helpers import get_invoxia_client

PLATFORMS: list[Platform] = [Platform.DEVICE_TRACKER, Platform.SENSOR]


def _import_gps_tracker():
    """Import gps_tracker module (blocking operation run in thread)."""
    import gps_tracker  # type: ignore
    return gps_tracker


def _import_coordinator():
    """Import the coordinator class (it imports gps_tracker, so run in thread)."""
    from .coordinator import GpsTrackerCoordinator

    return GpsTrackerCoordinator


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
        # Store empty list and skip platform forwarding since there are no entities to create
        # User can reload the integration after adding trackers to their account
        hass.data[DOMAIN][entry.entry_id][CLIENT] = client
        hass.data[DOMAIN][entry.entry_id][CONF_ENTITIES] = []
        hass.data[DOMAIN][entry.entry_id][TRACKERS] = []
        hass.data[DOMAIN][entry.entry_id][COORDINATORS] = []
        return True
    
    # Create the coordinators here, once, before the platforms are forwarded.
    # The device_tracker and sensor platforms are set up concurrently and both
    # need the same coordinators: creating them from one platform and reading
    # them from the other depends on which platform happens to start first.
    coordinator_class = await asyncio.to_thread(_import_coordinator)
    coordinators = [
        coordinator_class(hass, entry, client, tracker) for tracker in trackers
    ]

    # The first refresh also validates API access for every tracker. A tracker
    # that fails here (for example one without an active subscription) does
    # not prevent the setup: its entities stay unavailable until its
    # coordinator succeeds. Home Assistant does not log a failed first
    # refresh by itself, so log it here.
    for coordinator in coordinators:
        try:
            await coordinator.async_config_entry_first_refresh()
        except ConfigEntryNotReady as err:
            LOGGER.warning(
                "Failed to fetch initial data for tracker %s: %s",
                coordinator.tracker_label,
                err,
            )

    # Store all trackers in hass.data (including those that failed their
    # first refresh): coordinators automatically retry.
    hass.data[DOMAIN][entry.entry_id][CLIENT] = client
    hass.data[DOMAIN][entry.entry_id][CONF_ENTITIES] = []
    hass.data[DOMAIN][entry.entry_id][TRACKERS] = trackers
    hass.data[DOMAIN][entry.entry_id][COORDINATORS] = coordinators

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Re-evaluate entity availability when the options change (no reload)."""
    entry_data = hass.data[DOMAIN].get(entry.entry_id)
    if not entry_data:
        return
    for coordinator in entry_data[COORDINATORS]:
        coordinator.async_update_listeners()


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        client = hass.data[DOMAIN].get(entry.entry_id, {}).get(CLIENT)
        if client is not None and hasattr(client, "close"):
            await client.close()
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok
