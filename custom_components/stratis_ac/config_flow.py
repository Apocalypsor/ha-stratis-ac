"""Config flow for STRATIS AC."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    StratisApiClient,
    StratisAuthenticationError,
    StratisConnectionError,
    StratisError,
)
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_ACCESS_TOKEN_EXPIRES_AT,
    CONF_REFRESH_TOKEN,
    CONF_USER_ID,
    DOMAIN,
)
from .models import StratisProperty, StratisTokens


@dataclass(frozen=True, slots=True)
class ValidatedAccount:
    """Validated setup information."""

    user_id: str
    title: str
    tokens: StratisTokens


class StratisConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the STRATIS AC config flow."""

    VERSION = 1

    @staticmethod
    def _schema(default: str | None = None) -> vol.Schema:
        key = (
            vol.Required(CONF_REFRESH_TOKEN, default=default)
            if default
            else vol.Required(CONF_REFRESH_TOKEN)
        )
        return vol.Schema(
            {key: TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))}
        )

    async def _async_validate(self, refresh_token: str) -> ValidatedAccount:
        saved_tokens: StratisTokens | None = None

        async def async_capture_tokens(tokens: StratisTokens) -> None:
            nonlocal saved_tokens
            saved_tokens = tokens

        client = StratisApiClient(
            async_get_clientsession(self.hass),
            refresh_token=refresh_token,
            token_update_callback=async_capture_tokens,
        )
        user = await client.async_get_user()
        raw_properties = await client.async_get_properties()
        user_id = user.get("id")
        if not isinstance(user_id, str) or not user_id or saved_tokens is None:
            raise StratisAuthenticationError("STRATIS account identity is missing")

        properties = [
            parsed
            for raw in raw_properties
            if (parsed := StratisProperty.from_api(raw)) is not None
        ]
        title = properties[0].display_name if len(properties) == 1 else "STRATIS"
        return ValidatedAccount(user_id=user_id, title=title, tokens=saved_tokens)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Set up STRATIS from a rotating refresh token."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                account = await self._async_validate(user_input[CONF_REFRESH_TOKEN])
            except StratisAuthenticationError:
                errors["base"] = "invalid_auth"
            except StratisConnectionError:
                errors["base"] = "cannot_connect"
            except StratisError:
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(account.user_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=account.title,
                    data={
                        CONF_USER_ID: account.user_id,
                        CONF_ACCESS_TOKEN: account.tokens.access_token,
                        CONF_REFRESH_TOKEN: account.tokens.refresh_token,
                        CONF_ACCESS_TOKEN_EXPIRES_AT: account.tokens.expires_at,
                    },
                )

        return self.async_show_form(
            step_id="user", data_schema=self._schema(), errors=errors
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Start reauthentication after a refresh token failure."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Validate and persist a replacement refresh token."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                account = await self._async_validate(user_input[CONF_REFRESH_TOKEN])
            except StratisAuthenticationError:
                errors["base"] = "invalid_auth"
            except StratisConnectionError:
                errors["base"] = "cannot_connect"
            except StratisError:
                errors["base"] = "unknown"
            else:
                if account.user_id != self._reauth_entry.data.get(CONF_USER_ID):
                    errors["base"] = "wrong_account"
                else:
                    return self.async_update_reload_and_abort(
                        self._reauth_entry,
                        data_updates={
                            CONF_ACCESS_TOKEN: account.tokens.access_token,
                            CONF_REFRESH_TOKEN: account.tokens.refresh_token,
                            CONF_ACCESS_TOKEN_EXPIRES_AT: account.tokens.expires_at,
                        },
                    )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self._schema(),
            errors=errors,
        )
