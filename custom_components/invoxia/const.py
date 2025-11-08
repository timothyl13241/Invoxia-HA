"""Constants for the Invoxia (unofficial) integration."""
from __future__ import annotations

from datetime import timedelta
import logging

ATTRIBUTION = "Data provided by an unofficial client for Invoxia API."

CLIENT = "client"

DATA_UPDATE_INTERVAL = timedelta(seconds=420)

DOMAIN = "invoxia"

LOGGER = logging.getLogger(__package__)
