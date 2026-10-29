"""Actions for Seerr."""

from __future__ import annotations

from typing import Any

import probatio

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .api import SeerrClient, SeerrError
from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_IS_4K,
    ATTR_MEDIA_TYPE,
    ATTR_QUERY,
    ATTR_TMDB_ID,
    ATTR_YEAR,
    DOMAIN,
    MEDIA_TYPES,
    SERVICE_REQUEST,
    SERVICE_SEARCH,
)
from .media import async_request_media, async_search

QUERY = probatio.All(cv.string, probatio.Strip, probatio.Length(min=1))
COMMON = {
    probatio.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
    probatio.Optional(ATTR_MEDIA_TYPE): probatio.In(MEDIA_TYPES),
    probatio.Optional(ATTR_YEAR): probatio.All(
        probatio.Coerce(int), probatio.Range(min=1870, max=2200)
    ),
}

SEARCH_SCHEMA = probatio.Schema({probatio.Required(ATTR_QUERY): QUERY, **COMMON})


def _query_or_id(data: dict[str, Any]) -> dict[str, Any]:
    if ATTR_QUERY not in data and not (
        ATTR_TMDB_ID in data and ATTR_MEDIA_TYPE in data
    ):
        raise probatio.Invalid("Give a query, or a tmdb_id with a media_type")
    return data


REQUEST_SCHEMA = probatio.All(
    probatio.Schema(
        {
            probatio.Optional(ATTR_QUERY): QUERY,
            probatio.Optional(ATTR_TMDB_ID): cv.positive_int,
            probatio.Optional(ATTR_IS_4K, default=False): cv.boolean,
            **COMMON,
        }
    ),
    _query_or_id,
)


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the actions."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEARCH,
        _async_handle_search,
        schema=SEARCH_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REQUEST,
        _async_handle_request,
        schema=REQUEST_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )


def get_client(hass: HomeAssistant, entry_id: str | None = None) -> SeerrClient:
    """Return the client of the given entry, or of the only loaded one."""
    entries = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if entry_id is None or e.entry_id == entry_id
    ]
    if entry_id is not None and not entries:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entry_not_found",
            translation_placeholders={"entry_id": entry_id},
        )
    loaded = [e for e in entries if e.state is ConfigEntryState.LOADED]
    if len(loaded) != 1:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="no_server" if not loaded else "pick_server",
        )
    client: SeerrClient = loaded[0].runtime_data
    return client


def _action_error(err: SeerrError) -> HomeAssistantError:
    return HomeAssistantError(
        translation_domain=DOMAIN,
        translation_key="action_failed",
        translation_placeholders={"error": str(err)},
    )


async def _async_handle_search(call: ServiceCall) -> ServiceResponse:
    client = get_client(call.hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
    try:
        results = await async_search(
            client,
            call.data[ATTR_QUERY],
            call.data.get(ATTR_MEDIA_TYPE),
            call.data.get(ATTR_YEAR),
        )
    except SeerrError as err:
        raise _action_error(err) from err
    return {"results": [r.as_dict() for r in results]}


async def _async_handle_request(call: ServiceCall) -> ServiceResponse:
    client = get_client(call.hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
    try:
        outcome = await async_request_media(
            client,
            query=call.data.get(ATTR_QUERY),
            tmdb_id=call.data.get(ATTR_TMDB_ID),
            media_type=call.data.get(ATTR_MEDIA_TYPE),
            year=call.data.get(ATTR_YEAR),
            is_4k=call.data[ATTR_IS_4K],
        )
    except SeerrError as err:
        raise _action_error(err) from err
    if outcome["result"] in ("ambiguous", "not_found") and not call.return_response:
        # A caller that does not read the response would never learn of it.
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key=outcome["result"],
            translation_placeholders={
                "query": outcome["query"],
                "options": ", ".join(
                    f"{o['title']} ({o['year']}, {o['media_type']})"
                    for o in outcome.get("options", [])
                ),
            },
        )
    return outcome if call.return_response else None
