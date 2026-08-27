"""Tests for the STRATIS config and reauthentication flows."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.stratis_ac.api import StratisAuthenticationError
from custom_components.stratis_ac.const import (
    CONF_ACCESS_TOKEN,
    CONF_ACCESS_TOKEN_EXPIRES_AT,
    CONF_REFRESH_TOKEN,
    CONF_USER_ID,
    DOMAIN,
)
from custom_components.stratis_ac.models import StratisTokens


class SuccessfulClient:
    """A client that returns a rotated token and one property."""

    def __init__(self, _session, *, token_update_callback, **_kwargs) -> None:
        self._token_update_callback = token_update_callback

    async def async_get_user(self):
        await self._token_update_callback(
            StratisTokens("new-access", "new-refresh", 1234567890)
        )
        return {"id": "user-test"}

    async def async_get_properties(self):
        return [{"name": "properties/property-test", "display_name": "Test Property"}]


class InvalidAuthClient(SuccessfulClient):
    async def async_get_user(self):
        raise StratisAuthenticationError


@pytest.mark.asyncio
async def test_user_flow_stores_rotated_tokens(hass) -> None:
    with patch(
        "custom_components.stratis_ac.config_flow.StratisApiClient",
        SuccessfulClient,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_REFRESH_TOKEN: "captured-refresh"}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Test Property"
    assert result["data"] == {
        CONF_USER_ID: "user-test",
        CONF_ACCESS_TOKEN: "new-access",
        CONF_REFRESH_TOKEN: "new-refresh",
        CONF_ACCESS_TOKEN_EXPIRES_AT: 1234567890,
    }


@pytest.mark.asyncio
async def test_user_flow_reports_invalid_auth(hass) -> None:
    with patch(
        "custom_components.stratis_ac.config_flow.StratisApiClient",
        InvalidAuthClient,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_REFRESH_TOKEN: "invalid"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


@pytest.mark.asyncio
async def test_reauth_replaces_tokens(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="user-test",
        data={
            CONF_USER_ID: "user-test",
            CONF_ACCESS_TOKEN: "old-access",
            CONF_REFRESH_TOKEN: "old-refresh",
            CONF_ACCESS_TOKEN_EXPIRES_AT: 1,
        },
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.stratis_ac.config_flow.StratisApiClient",
        SuccessfulClient,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={
                "source": config_entries.SOURCE_REAUTH,
                "entry_id": entry.entry_id,
            },
            data=entry.data,
        )
        assert result["step_id"] == "reauth_confirm"
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_REFRESH_TOKEN: "replacement"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_ACCESS_TOKEN] == "new-access"
    assert entry.data[CONF_REFRESH_TOKEN] == "new-refresh"
