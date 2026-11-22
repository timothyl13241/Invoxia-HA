"""Data coordinator for Invoxia integration."""
from __future__ import annotations

import asyncio
from typing import Optional

from gps_tracker import AsyncClient, Tracker
from gps_tracker.client.exceptions import GpsTrackerException

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DATA_UPDATE_INTERVAL, DOMAIN, LOGGER
from .helpers import GpsTrackerData


class GpsTrackerCoordinator(DataUpdateCoordinator):
    """Coordinator to update GpsTracker entities."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: Optional[ConfigEntry],
        client: AsyncClient,
        tracker: Tracker,
    ) -> None:
        """Coordinator for single tracker."""
        # store references
        self._client = client
        self._tracker = tracker
        # keep a reference to the ConfigEntry when provided (may be None in some tests/legacy callers)
        self.config_entry = config_entry

        # Human readable label used in log messages: the coordinator name is
        # what Home Assistant prints when an update fails, so it must tell
        # the trackers of an account apart.
        self._tracker_label = f"{tracker.name} ({tracker.id})"

        super().__init__(
            hass,
            LOGGER,
            name=f"{DOMAIN} {self._tracker_label}",
            update_interval=DATA_UPDATE_INTERVAL,
        )

    @property
    def tracker_id(self) -> int:
        """Return the tracker ID."""
        return self._tracker.id

    @property
    def tracker_label(self) -> str:
        """Return the tracker name and ID, for log messages."""
        return self._tracker_label

    async def _async_update_data(self) -> GpsTrackerData:
        """Fetch data from API."""
        LOGGER.debug("Fetching data for Tracker %u", self._tracker.id)
        async with asyncio.timeout(10):
            try:
                locations, status = await asyncio.gather(
                    self._client.get_locations(self._tracker, max_count=1),
                    self._client.get_tracker_status(self._tracker),
                )
            except GpsTrackerException as err:
                # Home Assistant logs the failure when the tracker becomes
                # unavailable, with the coordinator name (tracker name and ID).
                raise UpdateFailed(err) from err

        if not locations:
            # The API answered but has no location for this tracker (new
            # tracker, expired subscription...).
            raise UpdateFailed("the API returned no location")

        return GpsTrackerData(
            latitude=locations[0].lat,
            longitude=locations[0].lng,
            accuracy=locations[0].precision,
            battery=status.battery,
            measured_at=locations[0].datetime,
        )
