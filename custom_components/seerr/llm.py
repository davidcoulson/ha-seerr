"""LLM tools for Seerr, so a voice assistant can find and request media."""

from __future__ import annotations

from typing import Any, override

import probatio

from homeassistant.components.llm import LLMTools
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.llm import (
    LLM_API_ASSIST,
    LLMContext,
    Tool,
    ToolAnnotations,
    ToolInput,
    ToolResult,
)

from .api import SeerrError
from .const import (
    ATTR_MEDIA_TYPE,
    ATTR_QUERY,
    ATTR_TMDB_ID,
    ATTR_YEAR,
    DOMAIN,
    MEDIA_TYPES,
)
from .media import async_request_media, async_search
from .services import (
    QUERY,
    YEAR,
    async_handle_auth_error,
    client_of,
    get_entry,
)

MEDIA_TYPE_DESCRIPTION = "movie or tv; leave out when the user did not say"
YEAR_DESCRIPTION = "Release or first air year, only when the user gave one"


class SearchMediaTool(Tool):
    """Look up movies and TV shows and whether they are on the media server."""

    name = f"{DOMAIN}__search_media"
    title = "Search movies and TV shows"
    description = (
        "Search for a movie or TV show by title. Each result has its TMDB id, "
        "year and status: available (already on Plex), partially_available, "
        "pending or processing (requested, not downloaded yet), or unknown "
        "(not requested). Use it to answer 'do we have X?'."
    )
    annotations = ToolAnnotations(
        read_only=True, destructive=False, idempotent=True, open_world=True
    )
    integration = DOMAIN
    parameters = probatio.Schema(
        {
            probatio.Required(ATTR_QUERY, description="Title to search for"): QUERY,
            probatio.Optional(
                ATTR_MEDIA_TYPE, description=MEDIA_TYPE_DESCRIPTION
            ): probatio.In(MEDIA_TYPES),
            probatio.Optional(ATTR_YEAR, description=YEAR_DESCRIPTION): YEAR,
        }
    )

    @override
    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> ToolResult:
        try:
            args = self.parameters(tool_input.tool_args)
            entry = _entry(hass)
            results = await async_search(
                client_of(entry),
                args[ATTR_QUERY],
                args.get(ATTR_MEDIA_TYPE),
                args.get(ATTR_YEAR),
            )
        except (probatio.Invalid, SeerrError, HomeAssistantError) as err:
            return _error(hass, err)
        return ToolResult(data={"results": [r.as_dict() for r in results[:10]]})


class RequestMediaTool(Tool):
    """Request a movie or TV show so it is downloaded to the media server."""

    name = f"{DOMAIN}__request_media"
    title = "Request a movie or TV show"
    description = (
        "Request a movie or TV show so it gets downloaded and added to Plex, "
        "for example 'add the TV show Dig to Plex'. Give the title as "
        "'query'. If the result is 'ambiguous', read the options to the user, "
        "ask which one they mean, then call again with that option's tmdb_id "
        "and media_type. Results already_available and already_requested "
        "mean nothing new was requested."
    )
    annotations = ToolAnnotations(destructive=False, idempotent=True, open_world=True)
    integration = DOMAIN
    parameters = probatio.Schema(
        {
            probatio.Optional(ATTR_QUERY, description="Title to request"): QUERY,
            probatio.Optional(
                ATTR_MEDIA_TYPE, description=MEDIA_TYPE_DESCRIPTION
            ): probatio.In(MEDIA_TYPES),
            probatio.Optional(ATTR_YEAR, description=YEAR_DESCRIPTION): YEAR,
            probatio.Optional(
                ATTR_TMDB_ID,
                description="TMDB id from an earlier search or ambiguous result; "
                "needs media_type",
            ): cv.positive_int,
        }
    )

    @override
    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> ToolResult:
        try:
            args: dict[str, Any] = self.parameters(tool_input.tool_args)
        except probatio.Invalid as err:
            return _error(hass, err)
        tmdb_id = args.get(ATTR_TMDB_ID)
        if ATTR_QUERY not in args and (tmdb_id is None or ATTR_MEDIA_TYPE not in args):
            return _error(
                hass, ValueError("Give a query, or a tmdb_id with a media_type")
            )
        try:
            outcome = await async_request_media(
                client_of(_entry(hass)),
                query=args.get(ATTR_QUERY),
                tmdb_id=tmdb_id,
                media_type=args.get(ATTR_MEDIA_TYPE),
                year=args.get(ATTR_YEAR),
            )
        except (SeerrError, HomeAssistantError) as err:
            return _error(hass, err)
        return ToolResult(data=outcome)


def _entry(hass: HomeAssistant) -> ConfigEntry:
    # shortcut: tools use the first loaded server; add a server argument if
    # anyone runs more than one Seerr.
    loaded = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.state is ConfigEntryState.LOADED
    ]
    return get_entry(hass, loaded[0].entry_id if loaded else None)


def _error(hass: HomeAssistant, err: Exception) -> ToolResult:
    if isinstance(err, SeerrError):
        for entry in hass.config_entries.async_loaded_entries(DOMAIN):
            async_handle_auth_error(hass, entry, err)
    return ToolResult(data={"error": str(err)}, error=True)


@callback
def async_get_tools(
    hass: HomeAssistant, llm_context: LLMContext, api_id: str
) -> LLMTools | None:
    """Return the Seerr tools when a server is set up."""
    if api_id != LLM_API_ASSIST or not any(
        e.state is ConfigEntryState.LOADED
        for e in hass.config_entries.async_entries(DOMAIN)
    ):
        return None
    return LLMTools(tools=[SearchMediaTool(), RequestMediaTool()])
