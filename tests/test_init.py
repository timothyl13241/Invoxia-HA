"""Tests for setup, failure visibility and Home Assistant deprecations."""
from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import MagicMock

from gps_tracker.client.exceptions import NoContentQuery
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.invoxia import device_tracker
from custom_components.invoxia.const import COORDINATORS, DOMAIN
from homeassistant.const import CONF_ENTITIES
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .conftest import make_location

TRACKER_ENTITY_ID = "device_tracker.bike"
COMPONENT_DIR = Path(device_tracker.__file__).parent


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


def _sensor_state(hass: HomeAssistant, key: str):
    entity_id = er.async_get(hass).async_get_entity_id("sensor", DOMAIN, f"1001_{key}")
    assert entity_id is not None, f"sensor {key} not registered"
    return hass.states.get(entity_id)


async def test_setup_creates_entities(
    hass: HomeAssistant, mock_client: MagicMock, config_entry: MockConfigEntry
) -> None:
    """The tracker and its sensors are created with the API values."""
    await _setup(hass, config_entry)

    state = hass.states.get(TRACKER_ENTITY_ID)
    assert state is not None
    assert state.state == "not_home"
    assert state.attributes["latitude"] == 44.0
    assert state.attributes["longitude"] == -0.5
    assert state.attributes["gps_accuracy"] == 35
    assert _sensor_state(hass, "battery").state == "87"
    assert _sensor_state(hass, "latitude").state == "44.0"
    assert _sensor_state(hass, "longitude").state == "-0.5"


async def test_platforms_share_one_coordinator_per_tracker(
    hass: HomeAssistant,
    mock_client: MagicMock,
    config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Every entity of a tracker uses the same coordinator, polled once at setup.

    The platforms are set up concurrently: they must not depend on which of
    them starts first to find (or create) the coordinators.
    """
    await _setup(hass, config_entry)

    entry_data = hass.data[DOMAIN][config_entry.entry_id]
    coordinators = entry_data[COORDINATORS]
    assert len(coordinators) == 1
    entities = entry_data[CONF_ENTITIES]
    assert len(entities) == 4  # device tracker, battery, latitude, longitude
    assert all(entity.coordinator is coordinators[0] for entity in entities)
    assert mock_client.get_locations.await_count == 1
    assert mock_client.get_tracker_status.await_count == 1
    assert "COORDINATORS key missing" not in caplog.text


async def test_battery_level_attribute_is_kept(
    hass: HomeAssistant, mock_client: MagicMock, config_entry: MockConfigEntry
) -> None:
    """The ``battery_level`` attribute stays available to existing automations."""
    await _setup(hass, config_entry)

    assert hass.states.get(TRACKER_ENTITY_ID).attributes["battery_level"] == 87


def test_no_deprecated_home_assistant_api() -> None:
    """The entity must not rely on APIs that Home Assistant is removing."""
    # ``battery_level`` is deprecated on tracker entities (removal in 2027.7).
    assert "battery_level" not in device_tracker.GpsTrackerEntity.__dict__
    # The ``TrackerEntity`` alias in ``device_tracker.config_entry`` is
    # deprecated (removal in 2027.6): import it from the integration root.
    source = (COMPONENT_DIR / "device_tracker.py").read_text(encoding="utf-8")
    assert "device_tracker.config_entry" not in source


async def test_first_refresh_failure_is_logged(
    hass: HomeAssistant,
    mock_client: MagicMock,
    config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A tracker failing at startup is unavailable and the reason is visible."""
    mock_client.get_locations.side_effect = NoContentQuery()

    await _setup(hass, config_entry)

    assert hass.states.get(TRACKER_ENTITY_ID).state == "unavailable"
    warnings = [
        record.getMessage()
        for record in caplog.records
        if record.levelno >= logging.WARNING and "Bike" in record.getMessage()
    ]
    assert any("No content" in message for message in warnings), caplog.text


async def test_empty_locations_do_not_raise(
    hass: HomeAssistant,
    mock_client: MagicMock,
    config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An empty location list makes the tracker unavailable, without a traceback."""
    mock_client.get_locations.return_value = []

    await _setup(hass, config_entry)

    assert hass.states.get(TRACKER_ENTITY_ID).state == "unavailable"
    assert "Unexpected error" not in caplog.text
    assert "IndexError" not in caplog.text


async def test_recovery_after_failure(
    hass: HomeAssistant, mock_client: MagicMock, config_entry: MockConfigEntry
) -> None:
    """A tracker failing at startup recovers on the next successful refresh."""
    mock_client.get_locations.side_effect = NoContentQuery()
    await _setup(hass, config_entry)
    assert hass.states.get(TRACKER_ENTITY_ID).state == "unavailable"

    mock_client.get_locations.side_effect = None
    mock_client.get_locations.return_value = [make_location()]
    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATORS][0]
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(TRACKER_ENTITY_ID).state == "not_home"


async def test_failure_message_identifies_the_tracker(
    hass: HomeAssistant,
    mock_client: MagicMock,
    config_entry: MockConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Failures after a successful setup name the tracker in the log."""
    await _setup(hass, config_entry)
    caplog.clear()

    mock_client.get_locations.side_effect = NoContentQuery()
    coordinator = hass.data[DOMAIN][config_entry.entry_id][COORDINATORS][0]
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert hass.states.get(TRACKER_ENTITY_ID).state == "unavailable"
    assert any(
        record.levelno >= logging.ERROR and "Bike" in record.getMessage()
        for record in caplog.records
    ), caplog.text
