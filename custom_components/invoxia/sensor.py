"""Platform for invoxia.sensor integration."""
from __future__ import annotations

from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from asyncio import Task

try:
    from homeassistant.helpers.location import async_detect_location_info
    HAS_LOCATION_HELPER = True
except ImportError:
    HAS_LOCATION_HELPER = False

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
        
        # Add geocoded location sensor only if the location helper is available
        if HAS_LOCATION_HELPER:
            entities.append(
                GpsTrackerGeocodedLocationSensor(coordinator, config_entry, tracker, hass)
            )

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


class GpsTrackerGeocodedLocationSensor(GpsTrackerSensorBase):
    """Geocoded location sensor for Invoxia GPS tracker."""

    _attr_icon = "mdi:map-marker"

    def __init__(
        self,
        coordinator: GpsTrackerCoordinator,
        config_entry: ConfigEntry,
        tracker: Tracker,
        hass: HomeAssistant,
    ) -> None:
        """Initialize the geocoded location sensor."""
        super().__init__(coordinator, config_entry, tracker)
        self._attr_unique_id = f"{tracker.id}_location"
        self._attr_name = "Location"
        self._hass = hass
        self._location_name: str | None = None
        self._last_latitude: float | None = None
        self._last_longitude: float | None = None
        self._geocoding_task: Task[None] | None = None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self.coordinator.data:
            latitude = self.coordinator.data.latitude
            longitude = self.coordinator.data.longitude
            
            # Only geocode if coordinates have changed
            if (latitude != self._last_latitude or longitude != self._last_longitude):
                # Cancel any pending geocoding task
                if self._geocoding_task and not self._geocoding_task.done():
                    self._geocoding_task.cancel()
                
                # Schedule the async geocoding
                self._geocoding_task = self._hass.async_create_task(
                    self._async_update_location(latitude, longitude)
                )
        super()._handle_coordinator_update()

    async def _async_update_location(self, latitude: float | None, longitude: float | None) -> None:
        """Update the geocoded location."""
        if not HAS_LOCATION_HELPER:
            LOGGER.debug("Location helper not available, skipping geocoding")
            return
            
        if latitude is None or longitude is None:
            if self._location_name is not None:
                self._location_name = None
                self._last_latitude = None
                self._last_longitude = None
                self.async_write_ha_state()
            return

        try:
            location_info = await async_detect_location_info(
                self._hass,
                latitude,
                longitude,
            )
            if location_info:
                # Build a human-readable location string
                parts = []
                if location_info.city:
                    parts.append(location_info.city)
                if location_info.region:
                    parts.append(location_info.region)
                if location_info.country:
                    parts.append(location_info.country)
                new_location_name = ", ".join(parts) if parts else None
            else:
                new_location_name = None
        except Exception as err:
            LOGGER.debug(
                "Could not geocode location for tracker %s: %s",
                self._tracker.id,
                err,
            )
            new_location_name = None

        # Only update state if location name changed
        if new_location_name != self._location_name:
            self._location_name = new_location_name
            self._last_latitude = latitude
            self._last_longitude = longitude
            self.async_write_ha_state()
        else:
            # Still update the cached coordinates even if name didn't change
            self._last_latitude = latitude
            self._last_longitude = longitude

    @property
    def native_value(self) -> str | None:
        """Return the geocoded location."""
        return self._location_name
