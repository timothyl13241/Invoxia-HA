"""Platform for invoxia.device_tracker integration."""
from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import timedelta

from gps_tracker import AsyncClient, Tracker
from gps_tracker.client.datatypes import Tracker01, TrackerIcon

from homeassistant.components.device_tracker import TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ENTITIES
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    ATTRIBUTION,
    CLIENT,
    CONF_STALE_AFTER,
    COORDINATORS,
    DOMAIN,
    LOGGER,
    TRACKERS,
)
from .coordinator import GpsTrackerCoordinator
from .helpers import GpsTrackerData

PARALLEL_UPDATES = 1

# Icon mapping for tracker types - defined here to avoid importing gps_tracker at module level in const.py
MDI_ICONS: Mapping[TrackerIcon, str] = {
    TrackerIcon.OTHER: "mdi:cube",
    TrackerIcon.HANDBAG: "mdi:purse",
    TrackerIcon.BRIEFCASE: "mdi:briefcase",
    TrackerIcon.SUITCASE: "mdi:bag-suitcase",
    TrackerIcon.BACKPACK: "mdi:bag-personal",
    TrackerIcon.BIKE: "mdi:bicycle-basket",
    TrackerIcon.BOAT: "mdi:sail-boat",
    TrackerIcon.CAR: "mdi:car-hatchback",
    TrackerIcon.CARAVAN: "mdi:caravan",
    TrackerIcon.CART: "mdi:dolly",
    TrackerIcon.KAYAK: "mdi:kayaking",
    TrackerIcon.LAPTOP: "mdi:laptop",
    TrackerIcon.MOTO: "mdi:motorbike",
    TrackerIcon.HELICOPTER: "mdi:helicopter",
    TrackerIcon.PLANE: "mdi:airplane",
    TrackerIcon.SCOOTER: "mdi:moped",
    TrackerIcon.TENT: "mdi:tent",
    TrackerIcon.TRUCK: "mdi:truck",
    TrackerIcon.TRACTOR: "mdi:tractor",
    TrackerIcon.DOG: "mdi:dog",
    TrackerIcon.CAT: "mdi:cat",
    TrackerIcon.PERSON: "mdi:face-man",
    TrackerIcon.GIRL: "mdi:face-woman",
    TrackerIcon.BACKHOE_LOADER: "mdi:excavator",
    TrackerIcon.ANIMAL: "mdi:paw",
    TrackerIcon.WOMAN: "mdi:human-female",
    TrackerIcon.MAN: "mdi:human-male",
    TrackerIcon.EBIKE: "mdi:scooter",
    TrackerIcon.BEEHIVE: "mdi:beehive-outline",
    TrackerIcon.CARPARK: "mdi:garage",
    TrackerIcon.ANTENNA: "mdi:antenna",
    TrackerIcon.HEALTH: "mdi:hospital-box",
    TrackerIcon.KEYS: "mdi:key-chain-variant",
    TrackerIcon.WASHER: "mdi:washing-machine",
    TrackerIcon.TV: "mdi:television",
    TrackerIcon.PHONE: "mdi:cellphone",
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the device_tracker platform."""
    # Trackers and coordinators are created (and refreshed once) in __init__.py
    entry_data = hass.data[DOMAIN].get(config_entry.entry_id)
    if entry_data is None:
        LOGGER.error(
            "No data found in hass.data for config entry %s; "
            "invoxia integration may not have initialized correctly",
            config_entry.entry_id,
        )
        return

    client: AsyncClient = entry_data[CLIENT]
    trackers: list[Tracker] = entry_data[TRACKERS]
    coordinators: list[GpsTrackerCoordinator] = entry_data[COORDINATORS]
    if not trackers:
        LOGGER.info("No trackers found for this account")
        return

    entities = [
        GpsTrackerEntity(coordinator, config_entry, client, tracker)
        for tracker, coordinator in zip(trackers, coordinators)
    ]

    hass.data[DOMAIN][config_entry.entry_id][CONF_ENTITIES].extend(entities)
    async_add_entities(entities, update_before_add=False)


class GpsTrackerEntity(CoordinatorEntity[GpsTrackerCoordinator], TrackerEntity):
    """Class for Invoxia™ GPS tracker devices."""

    _attr_attribution = ATTRIBUTION
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: GpsTrackerCoordinator,
        config_entry: ConfigEntry,
        client: AsyncClient,
        tracker: Tracker,
    ) -> None:
        """Store tracker main properties."""
        super().__init__(coordinator)

        # Attributes for update logic
        self._client: AsyncClient = client
        self._tracker: Tracker = tracker
        self.config_entry = config_entry

        # Static entity attributes
        if isinstance(tracker, Tracker01):
            self._attr_icon = MDI_ICONS[tracker.tracker_config.icon]
            self._attr_device_info = self._form_device_info(
                tracker
            )  # type:ignore[assignment]
            self._attr_name = self._tracker.name
            self._attr_unique_id = str(self._tracker.id)

        # Dynamic tracker-entity attributes
        self._tracker_data = GpsTrackerData(
            latitude=0.0,
            longitude=0.0,
            accuracy=0,
            battery=0,
        )
        self._last_available: bool | None = None
        self._update_attr()

    def _update_attr(self) -> None:
        """Update dynamic attributes."""
        LOGGER.debug("Updating attributes of Tracker %u", self._tracker.id)
        # The coordinator has no data until a first refresh succeeded: keep
        # the placeholder values in the meantime (the entity is unavailable).
        if self.coordinator.data is not None:
            self._tracker_data = self.coordinator.data

    def _is_stale(self) -> bool:
        """Return True if the last measurement is older than the stale threshold.

        The threshold is configured in minutes in the options flow; 0 disables it.
        """
        minutes = self.config_entry.options.get(CONF_STALE_AFTER, 0)
        measured_at = self._tracker_data.measured_at
        if not minutes or measured_at is None:
            return False
        return dt_util.utcnow() - measured_at > timedelta(minutes=minutes)

    @property
    def available(self) -> bool:
        """Return False when the API fails or the position is stale.

        A stale position is reported as unavailable instead of being republished
        as if it were fresh, so that consumers such as ``person`` ignore it.
        """
        return super().available and not self._is_stale()

    async def async_added_to_hass(self) -> None:
        """Remember the initial availability once the entity is registered."""
        await super().async_added_to_hass()
        self._last_available = self.available

    @callback
    def _handle_coordinator_update(self) -> None:
        """Write the state only when a new measurement or availability change.

        The coordinator refreshes every few minutes, but tracker entities force
        an update on each state write, which would bump ``last_updated`` even
        though the position did not change. ``person`` uses ``last_updated`` to
        pick the freshest source, so unchanged data must not be rewritten.
        """
        previous = self._tracker_data
        self._update_attr()
        available = self.available
        if (
            self._tracker_data == previous
            and available == self._last_available
            and self.hass is not None
            and self._last_available is not None
        ):
            return
        self._last_available = available
        super()._handle_coordinator_update()

    @property
    def extra_state_attributes(self) -> dict[str, int]:
        """Return the battery level as an attribute.

        Overriding ``battery_level`` on a tracker entity is deprecated (it
        stops working in Home Assistant 2027.7). The battery is exposed by a
        battery sensor, and kept here as an attribute so that existing
        automations and templates reading ``battery_level`` keep working.
        """
        return {"battery_level": self._tracker_data.battery}

    @property
    def source_type(self) -> str:
        """Define source type as being GPS."""
        return "gps"

    @property
    def location_accuracy(self) -> int:
        """Return accuration of last location data."""
        return self._tracker_data.accuracy

    @property
    def latitude(self) -> float | None:
        """Return last device latitude."""
        return self._tracker_data.latitude

    @property
    def longitude(self) -> float | None:
        """Return last device longitude."""
        return self._tracker_data.longitude

    @staticmethod
    def _form_device_info(tracker: Tracker01) -> DeviceInfo:
        """Extract device_info from tracker instance."""
        return {
            "hw_version": tracker.tracker_config.board_name,
            "identifiers": {(DOMAIN, tracker.serial)},
            "manufacturer": "Invoxia",
            "name": tracker.name,
            "sw_version": tracker.version,
            "model": tracker.tracker_config.board_name,
        }
