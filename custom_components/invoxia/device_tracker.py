"""Platform for invoxia.device_tracker integration."""
from __future__ import annotations

import asyncio
from collections.abc import Mapping

from gps_tracker import AsyncClient, Tracker
from gps_tracker.client.datatypes import Tracker01, TrackerIcon
from gps_tracker.client.exceptions import GpsTrackerException

from homeassistant.components.device_tracker.config_entry import TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ENTITIES
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, UpdateFailed

from .const import ATTRIBUTION, CLIENT, COORDINATORS, DOMAIN, LOGGER, TRACKERS
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
    client: AsyncClient = hass.data[DOMAIN][config_entry.entry_id][CLIENT]
    # Get trackers from hass.data (already fetched in __init__.py)
    entry_data = hass.data[DOMAIN].get(config_entry.entry_id)
    if entry_data is None:
        LOGGER.error(
            "No data found in hass.data for config entry %s; "
            "invoxia integration may not have initialized correctly",
            config_entry.entry_id,
        )
        return

    if TRACKERS not in entry_data:
        LOGGER.error(
            "TRACKERS key missing in hass.data for config entry %s; "
            "there may be a problem with invoxia integration initialization in __init__.py",
            config_entry.entry_id,
        )
        return

    trackers: list[Tracker] = entry_data[TRACKERS]
    if not trackers:
        LOGGER.info("No trackers found for this account")
        return

    coordinators = [
        GpsTrackerCoordinator(hass, config_entry, client, tracker) for tracker in trackers
    ]

    # Store coordinators in hass.data for reuse by sensor platform
    hass.data[DOMAIN][config_entry.entry_id][COORDINATORS] = coordinators

    # Perform first refresh for each coordinator.
    # If a coordinator fails, we still add the entity but it will be unavailable
    # until the next successful update.
    # Note: ConfigEntryNotReady is expected to be raised (and handled) in __init__.py
    # before forwarding entry setups; we catch it here defensively so an unexpected
    # occurrence does not break platform setup.
    for coordinator in coordinators:
        try:
            await coordinator.async_config_entry_first_refresh()
        except (GpsTrackerException, UpdateFailed, ConfigEntryNotReady) as err:
            # Log the error but don't fail the setup - the entity will be unavailable
            # until the coordinator successfully updates.
            # ConfigEntryNotReady should not normally occur here because validation is
            # already done in __init__.py, but we still catch it defensively.
            LOGGER.warning(
                "Failed to fetch initial data for tracker %s: %s",
                coordinator.tracker_id,
                err,
            )

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

        # Dynamic entity attributes
        self._attr_available: bool = True

        # Dynamic tracker-entity attributes
        self._tracker_data = GpsTrackerData(
            latitude=0.0,
            longitude=0.0,
            accuracy=0,
            battery=0,
        )
        self._update_attr()

    def _update_attr(self) -> None:
        """Update dynamic attributes."""
        LOGGER.debug("Updating attributes of Tracker %u", self._tracker.id)
        self._tracker_data = self.coordinator.data

    @callback
    def _handle_coordinator_update(self) -> None:
        self._update_attr()
        return super()._handle_coordinator_update()

    @property
    def battery_level(self) -> int | None:
        """Return tracker battery level."""
        return self._tracker_data.battery

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
