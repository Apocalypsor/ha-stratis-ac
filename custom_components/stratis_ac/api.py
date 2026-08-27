"""Async OAuth and API client for the undocumented STRATIS cloud API."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any
from urllib.parse import quote

import aiohttp

from .const import (
    API_BASE_URL,
    APP_ID,
    APP_VERSION,
    OAUTH_CLIENT_ID,
    OAUTH_REDIRECT_URI,
    OAUTH_SCOPE,
    OAUTH_TOKEN_URL,
    REQUEST_TIMEOUT,
    TOKEN_REFRESH_MARGIN,
    USER_AGENT,
)
from .models import StratisTokens

TokenUpdateCallback = Callable[[StratisTokens], Awaitable[None] | None]


class StratisError(Exception):
    """Base exception for STRATIS failures."""


class StratisAuthenticationError(StratisError):
    """Authentication failed or can no longer be refreshed."""


class StratisConnectionError(StratisError):
    """The STRATIS service could not be reached."""


class StratisApiError(StratisError):
    """The STRATIS service returned an unsuccessful response."""

    def __init__(
        self, status: int, message: str = "STRATIS API request failed"
    ) -> None:
        super().__init__(f"{message} (HTTP {status})")
        self.status = status


class StratisApiClient:
    """Manage STRATIS OAuth tokens and API calls."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        refresh_token: str,
        access_token: str | None = None,
        access_token_expires_at: float = 0,
        token_update_callback: TokenUpdateCallback | None = None,
    ) -> None:
        self._session = session
        self._refresh_token = refresh_token
        self._access_token = access_token
        self._access_token_expires_at = access_token_expires_at
        self._token_update_callback = token_update_callback
        self._refresh_lock = asyncio.Lock()

    @property
    def tokens(self) -> StratisTokens | None:
        """Return the current token pair when an access token is available."""
        if not self._access_token:
            return None
        return StratisTokens(
            access_token=self._access_token,
            refresh_token=self._refresh_token,
            expires_at=self._access_token_expires_at,
        )

    async def _async_notify_token_update(self, tokens: StratisTokens) -> None:
        if self._token_update_callback is None:
            return
        result = self._token_update_callback(tokens)
        if inspect.isawaitable(result):
            await result

    async def async_refresh_access_token(self, *, force: bool = False) -> str:
        """Return a valid access token, refreshing and persisting it if needed."""
        async with self._refresh_lock:
            if (
                not force
                and self._access_token
                and self._access_token_expires_at > time.time() + TOKEN_REFRESH_MARGIN
            ):
                return self._access_token

            form = {
                "scope": OAUTH_SCOPE,
                "refresh_token": self._refresh_token,
                "grant_type": "refresh_token",
                "r": "true",
                "redirect_uri": OAUTH_REDIRECT_URI,
                "brand": "stratis",
                "theme": "system",
                "client_id": OAUTH_CLIENT_ID,
            }
            try:
                async with asyncio.timeout(REQUEST_TIMEOUT):
                    response = await self._session.post(
                        OAUTH_TOKEN_URL,
                        data=form,
                        headers={
                            "Accept": "application/json",
                            "User-Agent": USER_AGENT,
                        },
                    )
                    if response.status in (400, 401, 403):
                        await response.read()
                        raise StratisAuthenticationError(
                            f"STRATIS token refresh failed (HTTP {response.status})"
                        )
                    if response.status >= 400:
                        await response.read()
                        raise StratisApiError(
                            response.status, "STRATIS token refresh failed"
                        )
                    payload = await self._async_json(response)
            except StratisError:
                raise
            except (TimeoutError, aiohttp.ClientError) as err:
                raise StratisConnectionError(
                    "Unable to reach STRATIS authentication"
                ) from err

            access_token = payload.get("access_token")
            refresh_token = payload.get("refresh_token")
            if not isinstance(access_token, str) or not access_token:
                raise StratisAuthenticationError(
                    "STRATIS token response did not include an access token"
                )
            if not isinstance(refresh_token, str) or not refresh_token:
                raise StratisAuthenticationError(
                    "STRATIS token response did not include a rotated refresh token"
                )
            try:
                expires_in = int(payload.get("expires_in", 3600))
            except (TypeError, ValueError):
                expires_in = 3600

            tokens = StratisTokens(
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=time.time() + expires_in,
            )

            # A rotating refresh token must be durable before any API call uses it.
            await self._async_notify_token_update(tokens)
            self._access_token = tokens.access_token
            self._refresh_token = tokens.refresh_token
            self._access_token_expires_at = tokens.expires_at
            return tokens.access_token

    async def _async_json(self, response: aiohttp.ClientResponse) -> dict[str, Any]:
        try:
            payload = await response.json(content_type=None)
        except (ValueError, aiohttp.ClientPayloadError) as err:
            raise StratisApiError(
                response.status, "STRATIS returned invalid JSON"
            ) from err
        if not isinstance(payload, dict):
            raise StratisApiError(
                response.status, "STRATIS returned an unexpected response"
            )
        return payload

    def _api_headers(self, access_token: str) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "User-Agent": USER_AGENT,
            "X-App-Id": APP_ID,
            "X-App-Version": APP_VERSION,
        }

    async def _async_request(
        self,
        method: str,
        path: str,
        *,
        json: Mapping[str, Any] | None = None,
        retry_auth: bool = True,
    ) -> dict[str, Any]:
        access_token = await self.async_refresh_access_token()
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                response = await self._session.request(
                    method,
                    f"{API_BASE_URL}{path}",
                    json=json,
                    headers=self._api_headers(access_token),
                )
                if response.status == 401 and retry_auth:
                    await response.read()
                    await self.async_refresh_access_token(force=True)
                    return await self._async_request(
                        method, path, json=json, retry_auth=False
                    )
                if response.status == 401:
                    await response.read()
                    raise StratisAuthenticationError(
                        "STRATIS rejected the refreshed access token"
                    )
                if response.status >= 400:
                    await response.read()
                    raise StratisApiError(response.status)
                if response.status == 204:
                    return {}
                return await self._async_json(response)
        except StratisError:
            raise
        except (TimeoutError, aiohttp.ClientError) as err:
            raise StratisConnectionError("Unable to reach the STRATIS API") from err

    async def async_get_user(self) -> dict[str, Any]:
        return await self._async_request("GET", "/v1/accounts/users/me")

    async def async_get_properties(self) -> list[dict[str, Any]]:
        payload = await self._async_request("GET", "/v2/properties?page_token=1")
        properties = payload.get("properties")
        return (
            [item for item in properties if isinstance(item, dict)]
            if isinstance(properties, list)
            else []
        )

    async def async_get_devices(self, property_id: str) -> list[dict[str, Any]]:
        safe_property_id = quote(property_id, safe="")
        payload = await self._async_request(
            "GET", f"/v1/properties/{safe_property_id}/devices?state=true"
        )
        devices = payload.get("devices")
        return (
            [item for item in devices if isinstance(item, dict)]
            if isinstance(devices, list)
            else []
        )

    async def async_set_thermostat(
        self,
        property_id: str,
        device_id: str,
        state: Mapping[str, Any],
    ) -> dict[str, Any]:
        safe_property_id = quote(property_id, safe="")
        safe_device_id = quote(device_id, safe="")
        return await self._async_request(
            "POST",
            f"/v1/properties/{safe_property_id}/devices/{safe_device_id}:setThermostat",
            json=state,
        )
