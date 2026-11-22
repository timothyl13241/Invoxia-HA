"""Helpers for Invoxia (unofficial) integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

if TYPE_CHECKING:
    from gps_tracker import AsyncClient, Config


@dataclass
class GpsTrackerData:
    """Dynamic data associated to a GPS Tracker."""

    latitude: float
    longitude: float
    accuracy: int
    battery: int
    # When the position was measured by the tracker (not when it was fetched)
    measured_at: datetime | None = None


def get_invoxia_client(hass: HomeAssistant, config: Config) -> AsyncClient:
    """Create an AsyncClient instance."""
    # Import at runtime to avoid import-time failures when package metadata is incomplete
    from gps_tracker import AsyncClient  # pylint: disable=import-outside-toplevel

    auth = AsyncClient.get_auth(config)
    session = async_create_clientsession(hass, auth=auth)
    return AsyncClient(config=config, session=session)
