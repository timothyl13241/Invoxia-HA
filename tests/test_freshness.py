"""Tests for location freshness: timestamp sensor, unchanged data, stale threshold."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.invoxia.const import CONF_STALE_AFTER, COORDINATORS, DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import make_location
from .test_init import TRACKER_ENTITY_ID, _sensor_state, _setup

MEASURED = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


async def _refresh(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id][COORDINATORS][0]
    await coordinator.async_refresh()
    await hass.async_block_till_done()


async def test_last_location_sensor(
    hass: HomeAssistant, mock_client: MagicMock, config_entry: MockConfigEntry, freezer
) -> None:
    """The sensor exposes when the tracker measured its position."""
    freezer.move_to(MEASURED)
    await _setup(hass, config_entry)
    assert _sensor_state(hass, "last_location").state == MEASURED.isoformat()


async def test_unchanged_measurement_does_not_touch_the_state(
    hass: HomeAssistant, mock_client: MagicMock, config_entry: MockConfigEntry, freezer
) -> None:
    """Republishing identical data must not bump last_updated."""
    freezer.move_to(MEASURED)
    await _setup(hass, config_entry)
    before = hass.states.get(TRACKER_ENTITY_ID).last_updated

    freezer.tick(timedelta(minutes=7))
    await _refresh(hass, config_entry)
    assert hass.states.get(TRACKER_ENTITY_ID).last_updated == before


async def test_new_measurement_updates_the_state(
    hass: HomeAssistant, mock_client: MagicMock, config_entry: MockConfigEntry, freezer
) -> None:
    """A new measurement is written, even at the same coordinates."""
    freezer.move_to(MEASURED)
    await _setup(hass, config_entry)
    before = hass.states.get(TRACKER_ENTITY_ID).last_updated

    freezer.tick(timedelta(minutes=7))
    mock_client.get_locations.return_value = [
        make_location(when=MEASURED + timedelta(minutes=6))
    ]
    await _refresh(hass, config_entry)
    assert hass.states.get(TRACKER_ENTITY_ID).last_updated > before


async def test_stale_threshold_disabled_by_default(
    hass: HomeAssistant, mock_client: MagicMock, config_entry: MockConfigEntry, freezer
) -> None:
    """Without the option, an old position stays available."""
    freezer.move_to(MEASURED)
    await _setup(hass, config_entry)
    freezer.tick(timedelta(days=3))
    await _refresh(hass, config_entry)
    assert hass.states.get(TRACKER_ENTITY_ID).state == "not_home"


async def test_stale_position_makes_tracker_unavailable(
    hass: HomeAssistant, mock_client: MagicMock, freezer
) -> None:
    """Past the threshold the tracker is unavailable, sensors keep the position."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="user@example.com",
        data={"username": "user@example.com", "password": "pw"},
        options={CONF_STALE_AFTER: 30},
    )
    freezer.move_to(MEASURED + timedelta(minutes=5))
    await _setup(hass, entry)
    assert hass.states.get(TRACKER_ENTITY_ID).state == "not_home"

    freezer.tick(timedelta(minutes=60))
    await _refresh(hass, entry)
    assert hass.states.get(TRACKER_ENTITY_ID).state == "unavailable"
    assert _sensor_state(hass, "latitude").state == "44.0"

    mock_client.get_locations.return_value = [
        make_location(when=MEASURED + timedelta(minutes=65))
    ]
    await _refresh(hass, entry)
    assert hass.states.get(TRACKER_ENTITY_ID).state == "not_home"


async def test_options_flow_reevaluates_without_reload(
    hass: HomeAssistant, mock_client: MagicMock, config_entry: MockConfigEntry, freezer
) -> None:
    """Saving the option applies immediately."""
    freezer.move_to(MEASURED + timedelta(hours=2))
    await _setup(hass, config_entry)
    assert hass.states.get(TRACKER_ENTITY_ID).state == "not_home"

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_STALE_AFTER: 30}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert config_entry.options[CONF_STALE_AFTER] == 30
    assert hass.states.get(TRACKER_ENTITY_ID).state == "unavailable"


async def test_person_keeps_the_phone_when_tracker_is_unchanged(
    hass: HomeAssistant, mock_client: MagicMock, config_entry: MockConfigEntry, freezer
) -> None:
    """Regression: a stale tracker republished must not override a fresher phone."""
    from homeassistant.setup import async_setup_component

    freezer.move_to(MEASURED)
    await _setup(hass, config_entry)
    hass.states.async_set(
        "device_tracker.phone", "home", {"source_type": "gps", "latitude": 1.0, "longitude": 1.0}
    )
    assert await async_setup_component(
        hass, "person", {"person": [{"name": "Test", "id": "test",
                                      "device_trackers": ["device_tracker.phone", TRACKER_ENTITY_ID]}]}
    )
    await hass.async_block_till_done()
    assert hass.states.get("person.test").state == "home"

    freezer.tick(timedelta(minutes=7))
    await _refresh(hass, config_entry)
    assert hass.states.get("person.test").state == "home"
