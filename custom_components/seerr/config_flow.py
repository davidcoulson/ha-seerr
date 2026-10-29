"""Config flow for Seerr."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import probatio
from yarl import URL

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_API_KEY, CONF_URL
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import SeerrAuthError, SeerrClient, SeerrConnectionError, SeerrError
from .const import DEFAULT_PORT, DOMAIN, LOGGER

URL_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.URL))
KEY_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


def normalize_url(raw: str) -> str:
    """Return a canonical server URL; a bare host gets http and port 5055."""
    raw = raw.strip()
    has_scheme = "://" in raw
    url = URL(raw if has_scheme else f"http://{raw}")
    if url.scheme not in ("http", "https") or not url.host:
        raise ValueError(raw)
    if not has_scheme and url.explicit_port is None:
        url = url.with_port(DEFAULT_PORT)
    return str(url.with_query(None).with_fragment(None)).rstrip("/")


class SeerrConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Seerr."""

    VERSION = 1

    async def _async_validate(
        self, url: str, api_key: str, errors: dict[str, str]
    ) -> dict[str, Any] | None:
        client = SeerrClient(async_get_clientsession(self.hass), url, api_key)
        try:
            return await client.async_get_user()
        except SeerrAuthError:
            errors[CONF_API_KEY] = "invalid_auth"
        except SeerrConnectionError:
            errors["base"] = "cannot_connect"
        except SeerrError:
            errors["base"] = "not_seerr"
        except Exception:
            LOGGER.exception("Unexpected error validating %s", url)
            errors["base"] = "unknown"
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the server URL and API key."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                url = normalize_url(user_input[CONF_URL])
            except ValueError:
                errors[CONF_URL] = "invalid_url"
            else:
                await self.async_set_unique_id(url)
                self._abort_if_unique_id_configured()
                if await self._async_validate(url, user_input[CONF_API_KEY], errors):
                    return self.async_create_entry(
                        title=f"Seerr ({URL(url).host})",
                        data={CONF_URL: url, CONF_API_KEY: user_input[CONF_API_KEY]},
                    )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                probatio.Schema(
                    {
                        probatio.Required(CONF_URL): URL_SELECTOR,
                        probatio.Required(CONF_API_KEY): KEY_SELECTOR,
                    }
                ),
                user_input,
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauthentication after the API key was rejected."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new API key."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None and await self._async_validate(
            entry.data[CONF_URL], user_input[CONF_API_KEY], errors
        ):
            return self.async_update_reload_and_abort(
                entry, data_updates={CONF_API_KEY: user_input[CONF_API_KEY]}
            )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=probatio.Schema(
                {probatio.Required(CONF_API_KEY): KEY_SELECTOR}
            ),
            description_placeholders={"url": entry.data[CONF_URL]},
            errors=errors,
        )
