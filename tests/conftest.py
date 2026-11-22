"""Shared fixtures for the Invoxia (unofficial) tests."""
from __future__ import annotations

from collections.abc import Generator
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from gps_tracker.client.datatypes import Device, TrackerData
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.invoxia.const import DOMAIN
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

TRACKER_JSON: dict[str, Any] = {
    "id": 1001,
    "type": "tracker_01",
    "created": "2024-01-01T10:00:00Z",
    "name": "Bike",
    "version": "tracker_LWT2v1-5.24.0-LoRa+Sigfox",
    "serial": "18b79efff00cb2c6",
    "version_build": "build",
    "model": "LWT2v1",
    "tracker_config": {
        "color": 1,
        "firmware_path": "",
        "icon": 7,
        "mode": 1,
        "network": "LoRa",
        "network_region": "EU",
        "notify_position": False,
        "notify_long_walk": False,
        "usage": "bike",
        "board_name": "LWT2v1",
    },
    "tracker_status": {
        "battery": 87,
        "begin_date": "2024-01-01T10:00:00Z",
        "network_operator": "Sigfox",
        "state": "ok",
        "stationary": 0,
        "sub_state": "",
    },
}


def make_tracker(**overrides: Any) -> Any:
    """Build a real ``Tracker01`` instance the way the library does."""
    data = deepcopy(TRACKER_JSON)
    data.update(overrides)
    return Device.get(data)


def make_location(
    lat: float = 44.0,
    lng: float = -0.5,
    when: datetime | None = None,
    precision: int = 35,
) -> TrackerData:
    """Build a location as returned by ``AsyncClient.get_locations``."""
    when = when or datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)
    return TrackerData(
        datetime=when.isoformat(),
        lat=lat,
        lng=lng,
        method=2,
        pkt_drop=0,
        precision=precision,
        uuid="00000000-0000-0000-0000-000000000001",
    )


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading of custom integrations in all tests."""


@pytest.fixture
def tracker() -> Any:
    """Return a tracker."""
    return make_tracker()


@pytest.fixture
def client(tracker: Any) -> MagicMock:
    """Return a fake ``AsyncClient`` serving a single tracker."""
    fake = MagicMock()
    fake.get_devices = AsyncMock(return_value=[tracker])
    fake.get_trackers = AsyncMock(return_value=[tracker])
    fake.get_locations = AsyncMock(return_value=[make_location()])
    fake.get_tracker_status = AsyncMock(return_value=tracker.tracker_status)
    fake.close = AsyncMock()
    return fake


@pytest.fixture
def mock_client(client: MagicMock) -> Generator[MagicMock]:
    """Patch the client factory used by the integration."""
    with (
        patch("custom_components.invoxia.get_invoxia_client", return_value=client),
        patch("custom_components.invoxia.config_flow.get_invoxia_client", return_value=client),
    ):
        yield client


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Return a config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="user@example.com",
        title="user@example.com",
        data={CONF_USERNAME: "user@example.com", CONF_PASSWORD: "secret"},
    )
