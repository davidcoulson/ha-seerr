"""Tests for setup and the search and request actions."""

from __future__ import annotations

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.seerr.const import DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .conftest import API, item, posted


@pytest.mark.parametrize(
    ("status", "state"),
    [(401, ConfigEntryState.SETUP_ERROR), (500, ConfigEntryState.SETUP_RETRY)],
)
async def test_setup_failures(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    status: int,
    state: ConfigEntryState,
) -> None:
    aioclient_mock.get(f"{API}/auth/me", status=status)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is state


async def test_search(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    response = await hass.services.async_call(
        DOMAIN,
        "search",
        {"query": "dig", "media_type": "movie"},
        blocking=True,
        return_response=True,
    )
    assert [(r["title"], r["year"], r["status"]) for r in response["results"]] == [
        ("The Dig", 2021, "unknown"),
        ("Dig", 2022, "available"),
    ]


async def test_search_encodes_query(
    hass: HomeAssistant, loaded: MockConfigEntry, seerr: AiohttpClientMocker
) -> None:
    await hass.services.async_call(
        DOMAIN, "search", {"query": "Dig! & co"}, blocking=True, return_response=True
    )
    url = seerr.mock_calls[-1][1]
    assert url.raw_query_string == "query=Dig%21%20%26%20co&page=1"


async def test_request_by_title(
    hass: HomeAssistant, loaded: MockConfigEntry, seerr: AiohttpClientMocker
) -> None:
    response = await hass.services.async_call(
        DOMAIN,
        "request",
        {"query": "Dig", "media_type": "tv", "year": 2015},
        blocking=True,
        return_response=True,
    )
    assert response["result"] == "requested"
    assert response["media"]["tmdb_id"] == 62120
    assert posted(seerr) == [
        {"mediaType": "tv", "mediaId": 62120, "is4k": False, "seasons": "all"}
    ]


async def test_request_by_id_without_response(
    hass: HomeAssistant, loaded: MockConfigEntry, seerr: AiohttpClientMocker
) -> None:
    await hass.services.async_call(
        DOMAIN,
        "request",
        {"tmdb_id": 532865, "media_type": "movie", "is_4k": True},
        blocking=True,
    )
    assert posted(seerr) == [{"mediaType": "movie", "mediaId": 532865, "is4k": True}]


async def test_request_already_available(
    hass: HomeAssistant, loaded: MockConfigEntry, seerr: AiohttpClientMocker
) -> None:
    response = await hass.services.async_call(
        DOMAIN,
        "request",
        {"query": "Dig", "media_type": "movie", "year": 2022},
        blocking=True,
        return_response=True,
    )
    assert response["result"] == "already_available"
    assert posted(seerr) == []


async def test_request_conflict_is_already_requested(
    hass: HomeAssistant, loaded: MockConfigEntry, seerr: AiohttpClientMocker
) -> None:
    seerr.clear_requests()
    seerr.post(f"{API}/request", status=409, text="Request already exists")
    response = await hass.services.async_call(
        DOMAIN,
        "request",
        {"tmdb_id": 62120, "media_type": "tv"},
        blocking=True,
        return_response=True,
    )
    assert response["result"] == "already_requested"


async def test_request_prefers_new_release(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    seerr: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    freezer.move_to("2026-10-28")
    response = await hass.services.async_call(
        DOMAIN, "request", {"query": "Dig"}, blocking=True, return_response=True
    )
    assert response["result"] == "requested"
    assert posted(seerr)[-1]["mediaId"] == 290826


async def test_request_ambiguous(
    hass: HomeAssistant, loaded: MockConfigEntry, freezer: FrozenDateTimeFactory
) -> None:
    freezer.move_to("2030-01-01")
    response = await hass.services.async_call(
        DOMAIN, "request", {"query": "Dig"}, blocking=True, return_response=True
    )
    assert response["result"] == "ambiguous"
    assert len(response["options"]) == 3
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN, "request", {"query": "Dig"}, blocking=True
        )
    assert err.value.translation_key == "ambiguous"
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN, "request", {"query": "Dig", "year": 1999}, blocking=True
        )
    assert err.value.translation_key == "not_found"


async def test_request_needs_query_or_id(
    hass: HomeAssistant, loaded: MockConfigEntry
) -> None:
    with pytest.raises(Exception, match="query"):
        await hass.services.async_call(DOMAIN, "request", {"tmdb_id": 1}, blocking=True)


async def test_server_error(
    hass: HomeAssistant, loaded: MockConfigEntry, seerr: AiohttpClientMocker
) -> None:
    seerr.clear_requests()
    seerr.get(f"{API}/search", status=500, text="boom test-key")
    with pytest.raises(HomeAssistantError, match="HTTP 500") as err:
        await hass.services.async_call(
            DOMAIN, "search", {"query": "x"}, blocking=True, return_response=True
        )
    assert "test-key" not in str(err.value)


@pytest.mark.parametrize(
    ("status", "body", "match"),
    [
        (302, None, "HTTP 302"),
        (200, {"results": [{"mediaType": "movie"}]}, "Unexpected search response"),
        (200, {"results": None}, "Unexpected search response"),
    ],
)
async def test_bad_search_responses(
    hass: HomeAssistant,
    loaded: MockConfigEntry,
    seerr: AiohttpClientMocker,
    status: int,
    body: object,
    match: str,
) -> None:
    seerr.clear_requests()
    seerr.get(
        f"{API}/search",
        status=status,
        json=body,
        headers={"Location": "http://elsewhere.example/"},
    )
    with pytest.raises(HomeAssistantError, match=match):
        await hass.services.async_call(
            DOMAIN, "search", {"query": "x"}, blocking=True, return_response=True
        )


async def test_nothing_new_to_request(
    hass: HomeAssistant, loaded: MockConfigEntry, seerr: AiohttpClientMocker
) -> None:
    seerr.clear_requests()
    seerr.post(f"{API}/request", status=202, json={})
    response = await hass.services.async_call(
        DOMAIN,
        "request",
        {"tmdb_id": 62120, "media_type": "tv"},
        blocking=True,
        return_response=True,
    )
    assert response["result"] == "already_requested"


async def test_pending_show_is_still_requested(
    hass: HomeAssistant, loaded: MockConfigEntry, seerr: AiohttpClientMocker
) -> None:
    # Seerr requests only the seasons that are missing.
    seerr.clear_requests()
    seerr.get(
        f"{API}/search",
        json={"results": [item(62120, "tv", "Dig", "2015-03-05", 91, status=2)]},
    )
    seerr.post(f"{API}/request", status=201, json={"id": 8})
    response = await hass.services.async_call(
        DOMAIN, "request", {"query": "Dig"}, blocking=True, return_response=True
    )
    assert response["result"] == "requested"
    assert posted(seerr)[-1]["mediaId"] == 62120


async def test_rejected_key_starts_reauth(
    hass: HomeAssistant, loaded: MockConfigEntry, seerr: AiohttpClientMocker
) -> None:
    seerr.clear_requests()
    seerr.get(f"{API}/search", status=401)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN, "search", {"query": "x"}, blocking=True, return_response=True
        )
    await hass.async_block_till_done()
    flows = hass.config_entries.flow.async_progress()
    assert [f["context"]["source"] for f in flows] == ["reauth"]


async def test_entry_selection(hass: HomeAssistant, loaded: MockConfigEntry) -> None:
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN,
            "search",
            {"query": "x", "config_entry_id": "nope"},
            blocking=True,
            return_response=True,
        )
    assert err.value.translation_key == "entry_not_found"
    await hass.config_entries.async_unload(loaded.entry_id)
    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            DOMAIN, "search", {"query": "x"}, blocking=True, return_response=True
        )
    assert err.value.translation_key == "no_server"
