"""Data coordinator for Invoxia integration."""
from __future__ import annotations

import asyncio
from typing import Optional

from async_timeout import timeout
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

        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=DATA_UPDATE_INTERVAL,
        )

    async def _async_update_data(self) -> GpsTrackerData:
        """Fetch data from API."""
        LOGGER.debug("Fetching data for Tracker %u", self._tracker.id)
        async with timeout(10):
            try:
                data = await asyncio.gather(
                    self._client.get_locations(self._tracker, max_count=1),
                    self._client.get_tracker_status(self._tracker),
                )
            except GpsTrackerException as err:
                LOGGER.warning("Could not fetch data for Tracker %u", self._tracker.id)
                raise UpdateFailed from err

        return GpsTrackerData(
            latitude=data[0][0].lat,
            longitude=data[0][0].lng,
            accuracy=data[0][0].precision,
            battery=data[1].battery,
        )
