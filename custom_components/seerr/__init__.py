"""Search and request movies and TV shows through Seerr."""

from __future__ import annotations

import importlib
import sys

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_URL
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    HomeAssistantError,
)
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service import async_register_admin_service
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .api import SeerrAuthError, SeerrClient, SeerrError
from .const import DOMAIN
from .services import async_setup_services

type SeerrConfigEntry = ConfigEntry[SeerrClient]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


def _forget_code(hass: HomeAssistant, package: str, domain: str) -> None:
    """Drop a package's modules so the next setup imports them from disk again.

    Home Assistant keeps its own copy of each imported integration module
    (loader.py: hass.data["components"], keyed "<domain>" and
    "<domain>.<platform>") next to Python's sys.modules; both have to go.
    """
    for cache, root in (
        (sys.modules, package),
        (hass.data.get("components", {}), domain),
        (hass.data.get("missing_platforms", {}), domain),
    ):
        for name in [n for n in cache if n == root or n.startswith(root + ".")]:
            del cache[name]
    importlib.invalidate_caches()  # or a file added since the last import may not be found


def _register_reload_code(hass: HomeAssistant) -> None:
    """Dev: seerr.reload_code loads the Python files from disk without a restart."""

    async def _reload_code(call: ServiceCall) -> None:
        entries = hass.config_entries.async_entries(DOMAIN)
        for entry in entries:
            if not await hass.config_entries.async_unload(entry.entry_id):
                raise HomeAssistantError(
                    f"{DOMAIN} did not unload; restart Home Assistant instead"
                )
        _forget_code(hass, __name__, DOMAIN)
        try:
            component = await (await async_get_integration(hass, DOMAIN)).async_get_component()
            await component.async_setup(hass, {})
        except Exception as err:
            # This handler stays registered, so the action works again once the code is fixed.
            raise HomeAssistantError(
                f"{DOMAIN} is unloaded: the new code did not load ({err}). "
                f"Fix it and call {DOMAIN}.reload_code again"
            ) from err
        failed = [e.title for e in entries if not await hass.config_entries.async_setup(e.entry_id)]
        if failed:
            raise HomeAssistantError(f"{DOMAIN} did not set up again for {failed}; see the log")

    async_register_admin_service(hass, DOMAIN, "reload_code", _reload_code)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the integration's actions."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: SeerrConfigEntry) -> bool:
    """Set up Seerr from a config entry."""
    _register_reload_code(hass)
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
