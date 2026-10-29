"""Tests for the config flow."""

from __future__ import annotations

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.seerr.const import DOMAIN
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_API_KEY, CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import API, URL_BASE


async def test_user_flow(hass: HomeAssistant, seerr: AiohttpClientMocker) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: "10.2.6.95", CONF_API_KEY: "k"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Seerr Requests (10.2.6.95)"
    assert result["data"] == {CONF_URL: URL_BASE, CONF_API_KEY: "k"}


@pytest.mark.parametrize(
    ("kwargs", "field", "error"),
    [
        ({"status": 401}, CONF_API_KEY, "invalid_auth"),
        ({"exc": TimeoutError()}, "base", "cannot_connect"),
        ({"text": "<html>"}, "base", "not_seerr"),
        ({"exc": RuntimeError()}, "base", "unknown"),
    ],
)
async def test_user_flow_errors(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    kwargs: dict,
    field: str,
    error: str,
) -> None:
    aioclient_mock.get(f"{API}/auth/me", **kwargs)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: URL_BASE, CONF_API_KEY: "k"}
    )
    assert result["errors"] == {field: error}


async def test_invalid_url_and_duplicate(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: "ftp://x", CONF_API_KEY: "k"}
    )
    assert result["errors"] == {CONF_URL: "invalid_url"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: f"{URL_BASE}/", CONF_API_KEY: "k"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth(
    hass: HomeAssistant, entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    entry.add_to_hass(hass)
    aioclient_mock.get(f"{API}/auth/me", status=403)
    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "bad"}
    )
    assert result["errors"] == {CONF_API_KEY: "invalid_auth"}
    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{API}/auth/me", json={"id": 1})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "new"}
    )
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_API_KEY] == "new"
