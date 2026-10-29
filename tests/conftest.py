"""Fixtures for Seerr tests."""

from __future__ import annotations

from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.seerr.const import DOMAIN
from homeassistant.const import CONF_API_KEY, CONF_URL
from homeassistant.core import HomeAssistant

URL_BASE = "http://10.2.6.95:5055"
API = f"{URL_BASE}/api/v1"


def item(
    tmdb_id: int,
    media_type: str,
    title: str,
    date: str,
    votes: int = 0,
    status: int | None = None,
) -> dict[str, Any]:
    """Return a search item shaped like Seerr 3.5's."""
    key = (
        ("title", "releaseDate") if media_type == "movie" else ("name", "firstAirDate")
    )
    result: dict[str, Any] = {
        "id": tmdb_id,
        "mediaType": media_type,
        key[0]: title,
        key[1]: date,
        "overview": f"About {title}",
        "voteCount": votes,
    }
    if status is not None:
        result["mediaInfo"] = {"status": status}
    return result


# The live results for "dig" (Seerr 3.5.1, October 2026), plus a person.
DIG_RESULTS = [
    item(62120, "tv", "Dig", "2015-03-05", 91),
    item(290826, "tv", "Dig", "2026-01-01", 0),
    item(532865, "movie", "The Dig", "2021-01-14", 1414),
    item(816956, "movie", "Dig", "2022-09-23", 45, status=5),
    {"id": 1619444, "mediaType": "person", "name": "Dig Wayne"},
]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations."""


@pytest.fixture
def entry() -> MockConfigEntry:
    """Return a config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Seerr (10.2.6.95)",
        unique_id=URL_BASE,
        data={CONF_URL: URL_BASE, CONF_API_KEY: "test-key"},
    )


@pytest.fixture
def seerr(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    """Mock a working Seerr server whose search returns DIG_RESULTS."""
    aioclient_mock.get(f"{API}/auth/me", json={"id": 1, "displayName": "Admin"})
    aioclient_mock.get(f"{API}/search", json={"results": DIG_RESULTS})
    aioclient_mock.post(f"{API}/request", json={"id": 7}, status=201)
    return aioclient_mock


@pytest.fixture
async def loaded(
    hass: HomeAssistant, entry: MockConfigEntry, seerr: AiohttpClientMocker
) -> MockConfigEntry:
    """Set up the integration."""
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def posted(mock: AiohttpClientMocker) -> list[Any]:
    """Return the bodies posted to /request."""
    return [data for method, url, data, _ in mock.mock_calls if method == "POST"]
