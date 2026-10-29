"""Search and request movies and TV shows through Seerr."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import SeerrAuthError, SeerrClient, SeerrError
from .const import DOMAIN
from .services import async_setup_services

type SeerrConfigEntry = ConfigEntry[SeerrClient]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the integration's actions."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: SeerrConfigEntry) -> bool:
    """Set up Seerr from a config entry."""
    client = SeerrClient(
        async_get_clientsession(hass), entry.data[CONF_URL], entry.data[CONF_API_KEY]
    )
    try:
        await client.async_get_user()
    except SeerrAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except SeerrError as err:
        raise ConfigEntryNotReady(str(err)) from err
    entry.runtime_data = client
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SeerrConfigEntry) -> bool:
    """Unload a config entry."""
    return True
