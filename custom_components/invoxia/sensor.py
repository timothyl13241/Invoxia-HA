"""Platform for invoxia.sensor integration."""
from __future__ import annotations

from gps_tracker import AsyncClient, Tracker
from gps_tracker.client.exceptions import GpsTrackerException

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ENTITIES, PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity, UpdateFailed

from .const import ATTRIBUTION, CLIENT, COORDINATORS, DOMAIN, LOGGER, TRACKERS
from .coordinator import GpsTrackerCoordinator

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
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

    # Reuse coordinators created by device_tracker platform
    coordinators = entry_data.get(COORDINATORS)
    if coordinators is None:
        LOGGER.error(
            "COORDINATORS key missing in hass.data for config entry %s; "
            "device_tracker platform should have created them first",
            config_entry.entry_id,
        )
        # Fall back to creating coordinators if they don't exist
        coordinators = [
            GpsTrackerCoordinator(hass, config_entry, client, tracker) for tracker in trackers
        ]
        # Perform first refresh for each coordinator
        for coordinator in coordinators:
            try:
                await coordinator.async_config_entry_first_refresh()
            except (GpsTrackerException, UpdateFailed, ConfigEntryNotReady) as err:
                LOGGER.warning(
                    "Failed to fetch initial data for tracker %s: %s",
                    coordinator.tracker_id,
                    err,
                )

    entities = []
    for tracker, coordinator in zip(trackers, coordinators):
        # Create battery, latitude, and longitude sensors for each tracker
        entities.extend([
            GpsTrackerBatterySensor(coordinator, config_entry, tracker),
            GpsTrackerLatitudeSensor(coordinator, config_entry, tracker),
            GpsTrackerLongitudeSensor(coordinator, config_entry, tracker),
        ])

    hass.data[DOMAIN][config_entry.entry_id][CONF_ENTITIES].extend(entities)
    async_add_entities(entities, update_before_add=False)


class GpsTrackerSensorBase(CoordinatorEntity[GpsTrackerCoordinator], SensorEntity):
    """Base class for Invoxia GPS tracker sensor entities."""

    _attr_attribution = ATTRIBUTION
    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: GpsTrackerCoordinator,
        config_entry: ConfigEntry,
        tracker: Tracker,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._tracker = tracker
        self.config_entry = config_entry

        # Set device info to link sensor to the tracker device
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, tracker.serial)},
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success


class GpsTrackerBatterySensor(GpsTrackerSensorBase):
    """Battery sensor for Invoxia GPS tracker."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: GpsTrackerCoordinator,
        config_entry: ConfigEntry,
        tracker: Tracker,
    ) -> None:
        """Initialize the battery sensor."""
        super().__init__(coordinator, config_entry, tracker)
        self._attr_unique_id = f"{tracker.id}_battery"
        self._attr_name = "Battery"

    @property
    def native_value(self) -> int | None:
        """Return the battery level."""
        if self.coordinator.data:
            return self.coordinator.data.battery
        return None


class GpsTrackerLatitudeSensor(GpsTrackerSensorBase):
    """Latitude sensor for Invoxia GPS tracker."""

    _attr_icon = "mdi:latitude"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: GpsTrackerCoordinator,
        config_entry: ConfigEntry,
        tracker: Tracker,
    ) -> None:
        """Initialize the latitude sensor."""
        super().__init__(coordinator, config_entry, tracker)
        self._attr_unique_id = f"{tracker.id}_latitude"
        self._attr_name = "Latitude"

    @property
    def native_value(self) -> float | None:
        """Return the latitude."""
        if self.coordinator.data:
            return self.coordinator.data.latitude
        return None


class GpsTrackerLongitudeSensor(GpsTrackerSensorBase):
    """Longitude sensor for Invoxia GPS tracker."""

    _attr_icon = "mdi:longitude"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: GpsTrackerCoordinator,
        config_entry: ConfigEntry,
        tracker: Tracker,
    ) -> None:
        """Initialize the longitude sensor."""
        super().__init__(coordinator, config_entry, tracker)
        self._attr_unique_id = f"{tracker.id}_longitude"
        self._attr_name = "Longitude"

    @property
    def native_value(self) -> float | None:
        """Return the longitude."""
        if self.coordinator.data:
            return self.coordinator.data.longitude
        return None
