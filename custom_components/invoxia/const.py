"""Constants for the Invoxia (unofficial) integration."""
from __future__ import annotations

from datetime import timedelta
import logging

ATTRIBUTION = "Data provided by an unofficial client for Invoxia API."

CLIENT = "client"

CONF_STALE_AFTER = "stale_after"
"""Option: age (in minutes) after which a position is considered stale (0 = never)."""

COORDINATORS = "coordinators"

DATA_UPDATE_INTERVAL = timedelta(seconds=420)

DOMAIN = "invoxia"

LOGGER = logging.getLogger(__package__)

TRACKERS = "trackers"
