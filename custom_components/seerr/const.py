"""Constants for the Seerr integration."""

from __future__ import annotations

import logging
from typing import Final

DOMAIN: Final = "seerr"
LOGGER = logging.getLogger(__package__)

DEFAULT_PORT: Final = 5055

ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"
ATTR_QUERY: Final = "query"
ATTR_MEDIA_TYPE: Final = "media_type"
ATTR_YEAR: Final = "year"
ATTR_TMDB_ID: Final = "tmdb_id"
ATTR_IS_4K: Final = "is_4k"

SERVICE_SEARCH: Final = "search"
SERVICE_REQUEST: Final = "request"

MEDIA_TYPES: Final = ("movie", "tv")
