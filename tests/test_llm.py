"""Tests for the LLM tools."""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import llm
from homeassistant.setup import async_setup_component

from .conftest import API, posted


async def _api(hass: HomeAssistant) -> llm.APIInstance:
    assert await async_setup_component(hass, "homeassistant", {})
    assert await async_setup_component(hass, "llm", {})
    return await llm.async_get_api(
        hass,
        llm.LLM_API_ASSIST,
        llm.LLMContext(
            platform="test",
            context=Context(),
            language="en",
            assistant="conversation",
            device_id=None,
        ),
    )


async def _call(api: llm.APIInstance, name: str, **args: object) -> dict:
    result = await api.async_call_tool(llm.ToolInput(tool_name=name, tool_args=args))
    return result.data if isinstance(result, llm.ToolResult) else result


async def test_no_tools_without_server(hass: HomeAssistant) -> None:
    api = await _api(hass)
    assert not [t for t in api.tools if t.name.startswith("seerr__")]


async def test_tools(
    hass: HomeAssistant, loaded: MockConfigEntry, seerr: AiohttpClientMocker
) -> None:
    api = await _api(hass)
    names = {t.name for t in api.tools}
    assert {"seerr__search_media", "seerr__request_media"} <= names

    result = await _call(api, "seerr__search_media", query="dig", year=2021)
    assert [r["title"] for r in result["results"]] == ["The Dig"]

    result = await _call(api, "seerr__request_media", query="Dig")
    assert result["result"] == "ambiguous"
    result = await _call(api, "seerr__request_media", tmdb_id=62120, media_type="tv")
    assert result["result"] == "requested"
    assert posted(seerr)[-1]["mediaId"] == 62120

    result = await _call(api, "seerr__request_media", tmdb_id=62120)
    assert "error" in result

    seerr.clear_requests()
    seerr.get(f"{API}/search", status=500)
    result = await _call(api, "seerr__search_media", query="x")
    assert "error" in result
    result = await _call(api, "seerr__request_media", query="x")
    assert "error" in result
