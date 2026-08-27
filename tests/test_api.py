"""Tests for OAuth rotation and STRATIS API retry behavior."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from custom_components.stratis_ac.api import (
    StratisApiClient,
    StratisAuthenticationError,
)
from custom_components.stratis_ac.const import OAUTH_TOKEN_URL


class FakeResponse:
    """Minimal aiohttp response used by the API client."""

    def __init__(self, status: int, payload: dict[str, Any]) -> None:
        self.status = status
        self._payload = payload

    async def json(self, *, content_type: str | None = None) -> dict[str, Any]:
        return self._payload

    async def read(self) -> bytes:
        return b""


@pytest.mark.asyncio
async def test_refresh_rotates_and_persists_before_use() -> None:
    session = AsyncMock()
    session.post.return_value = FakeResponse(
        200,
        {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_in": 3600,
        },
    )
    persisted = []

    async def save_tokens(tokens) -> None:
        persisted.append(tokens)

    client = StratisApiClient(
        session,
        refresh_token="old-refresh",
        token_update_callback=save_tokens,
    )

    access_token = await client.async_refresh_access_token()

    assert access_token == "new-access"
    assert client.tokens is not None
    assert client.tokens.refresh_token == "new-refresh"
    assert persisted == [client.tokens]
    assert session.post.call_args.args[0] == OAUTH_TOKEN_URL
    assert session.post.call_args.kwargs["data"]["grant_type"] == "refresh_token"
    assert session.post.call_args.kwargs["data"]["refresh_token"] == "old-refresh"


@pytest.mark.asyncio
async def test_valid_access_token_is_reused() -> None:
    session = AsyncMock()
    client = StratisApiClient(
        session,
        refresh_token="refresh",
        access_token="cached-access",
        access_token_expires_at=9_999_999_999,
    )

    assert await client.async_refresh_access_token() == "cached-access"
    session.post.assert_not_awaited()


@pytest.mark.asyncio
async def test_api_401_forces_one_refresh_and_retry() -> None:
    session = AsyncMock()
    session.post.return_value = FakeResponse(
        200,
        {
            "access_token": "refreshed-access",
            "refresh_token": "rotated-refresh",
            "expires_in": 3600,
        },
    )
    session.request.side_effect = [
        FakeResponse(401, {}),
        FakeResponse(200, {"properties": []}),
    ]
    client = StratisApiClient(
        session,
        refresh_token="old-refresh",
        access_token="expired-early",
        access_token_expires_at=9_999_999_999,
    )

    assert await client.async_get_properties() == []
    assert session.request.await_count == 2
    assert session.post.await_count == 1
    second_headers = session.request.await_args_list[1].kwargs["headers"]
    assert second_headers["Authorization"] == "Bearer refreshed-access"


@pytest.mark.asyncio
async def test_invalid_refresh_token_raises_authentication_error() -> None:
    session = AsyncMock()
    session.post.return_value = FakeResponse(400, {})
    client = StratisApiClient(session, refresh_token="invalid")

    with pytest.raises(StratisAuthenticationError):
        await client.async_refresh_access_token()
