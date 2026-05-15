"""Tests for authful_mcp_proxy.outbound_auth — outbound auth mode factory.

These tests exercise the httpx.Auth classes directly without spinning up a
FastMCP server, by:

- Mocking ``get_access_token`` for forward mode
- Using ``respx`` is overkill here; instead we patch ``httpx.AsyncClient.post``
  for the client_credentials refresh path
- For static mode, just inspecting the resulting request headers
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from authful_mcp_proxy.config import WebConfig
from authful_mcp_proxy.outbound_auth import (
    ForwardSessionTokenAuth,
    OAuthClientCredentialsAuth,
    StaticHeaderAuth,
    build_outbound_auth,
)


def _base_keycloak_kwargs() -> dict:
    return {
        "auth_provider": "keycloak",
        "base_url": "https://mcp.example.com",
        "issuer_url": "https://kc.example.com/realms/r",
    }


class TestBuildOutboundAuthDispatch:
    """The factory should pick the right httpx.Auth shape for each mode."""

    def test_forward_returns_forward_auth(self):
        config = WebConfig(**_base_keycloak_kwargs())
        auth = build_outbound_auth(config)
        assert isinstance(auth, ForwardSessionTokenAuth)

    def test_static_returns_static_auth_with_default_header_name(self):
        config = WebConfig(
            **_base_keycloak_kwargs(),
            outbound_auth="static",
            outbound_header_value="Bearer abc123",
        )
        auth = build_outbound_auth(config)
        assert isinstance(auth, StaticHeaderAuth)
        assert auth.header_name == "Authorization"
        assert auth.header_value == "Bearer abc123"

    def test_static_returns_static_auth_with_custom_header_name(self):
        config = WebConfig(
            **_base_keycloak_kwargs(),
            outbound_auth="static",
            outbound_header_name="X-API-Key",
            outbound_header_value="abc123",
        )
        auth = build_outbound_auth(config)
        assert isinstance(auth, StaticHeaderAuth)
        assert auth.header_name == "X-API-Key"
        assert auth.header_value == "abc123"

    def test_oauth_cc_returns_cc_auth(self):
        config = WebConfig(
            **_base_keycloak_kwargs(),
            outbound_auth="oauth-client-credentials",
            outbound_client_id="ocid",
            outbound_client_secret="osec",
            outbound_token_url="https://idp.example.com/token",
        )
        auth = build_outbound_auth(config)
        assert isinstance(auth, OAuthClientCredentialsAuth)
        assert auth.token_url == "https://idp.example.com/token"
        assert auth.client_id == "ocid"
        assert auth.client_secret == "osec"

    def test_unknown_outbound_auth_raises(self):
        config = WebConfig(**_base_keycloak_kwargs())
        config.outbound_auth = "made-up-mode"  # type: ignore[assignment]  # ty: ignore[invalid-assignment]
        with pytest.raises(ValueError, match="Unknown outbound_auth"):
            build_outbound_auth(config)


class TestForwardSessionTokenAuth:
    """Forward mode reads from FastMCP's per-session access token accessor."""

    @pytest.mark.asyncio
    async def test_injects_bearer_token_when_session_token_present(self):
        mock_token = MagicMock(token="session-token-xyz")
        with patch(
            "authful_mcp_proxy.outbound_auth.get_access_token",
            return_value=mock_token,
        ):
            auth = ForwardSessionTokenAuth()
            request = httpx.Request("GET", "https://upstream.example.com/")
            flow = auth.async_auth_flow(request)
            yielded = await flow.__anext__()

        assert yielded.headers["Authorization"] == "Bearer session-token-xyz"

    @pytest.mark.asyncio
    async def test_raises_when_no_session_token(self):
        with patch(
            "authful_mcp_proxy.outbound_auth.get_access_token", return_value=None
        ):
            auth = ForwardSessionTokenAuth()
            request = httpx.Request("GET", "https://upstream.example.com/")
            flow = auth.async_auth_flow(request)
            with pytest.raises(RuntimeError, match="No inbound session access token"):
                await flow.__anext__()

    @pytest.mark.asyncio
    async def test_raises_when_session_token_has_empty_value(self):
        mock_token = MagicMock(token="")
        with patch(
            "authful_mcp_proxy.outbound_auth.get_access_token",
            return_value=mock_token,
        ):
            auth = ForwardSessionTokenAuth()
            request = httpx.Request("GET", "https://upstream.example.com/")
            flow = auth.async_auth_flow(request)
            with pytest.raises(RuntimeError):
                await flow.__anext__()


class TestStaticHeaderAuth:
    """Static mode unconditionally injects the configured header value."""

    def test_injects_authorization_bearer_header(self):
        auth = StaticHeaderAuth(
            header_name="Authorization", header_value="Bearer abc123"
        )
        request = httpx.Request("GET", "https://upstream.example.com/")
        # auth_flow is a sync generator; iterate once
        flow = auth.auth_flow(request)
        yielded = next(flow)
        assert yielded.headers["Authorization"] == "Bearer abc123"

    def test_injects_custom_header_name(self):
        auth = StaticHeaderAuth(header_name="X-API-Key", header_value="abc123")
        request = httpx.Request("GET", "https://upstream.example.com/")
        flow = auth.auth_flow(request)
        yielded = next(flow)
        assert yielded.headers["X-API-Key"] == "abc123"
        assert "Authorization" not in yielded.headers

    def test_overwrites_existing_header(self):
        auth = StaticHeaderAuth(
            header_name="Authorization", header_value="Bearer fresh"
        )
        request = httpx.Request(
            "GET",
            "https://upstream.example.com/",
            headers={"Authorization": "Bearer stale"},
        )
        flow = auth.auth_flow(request)
        yielded = next(flow)
        assert yielded.headers["Authorization"] == "Bearer fresh"


class TestOAuthClientCredentialsAuth:
    """oauth-client-credentials obtains, caches, and refreshes a service-account
    token via the OAuth client_credentials grant."""

    @pytest.mark.asyncio
    async def test_initial_request_fetches_and_injects_token(self):
        auth = OAuthClientCredentialsAuth(
            token_url="https://idp.example.com/token",
            client_id="cid",
            client_secret="csec",
        )

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "access_token": "fresh-token",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_response

        with patch(
            "authful_mcp_proxy.outbound_auth.httpx.AsyncClient",
            return_value=mock_client,
        ):
            request = httpx.Request("GET", "https://upstream.example.com/")
            flow = auth.async_auth_flow(request)
            yielded = await flow.__anext__()

        assert yielded.headers["Authorization"] == "Bearer fresh-token"
        # POST was made to the configured token URL with the right form data.
        mock_client.post.assert_called_once()
        call = mock_client.post.call_args
        assert call.args[0] == "https://idp.example.com/token"
        assert call.kwargs["data"]["grant_type"] == "client_credentials"
        assert call.kwargs["data"]["client_id"] == "cid"
        assert call.kwargs["data"]["client_secret"] == "csec"

    @pytest.mark.asyncio
    async def test_second_request_within_validity_reuses_cached_token(self):
        auth = OAuthClientCredentialsAuth(
            token_url="https://idp.example.com/token",
            client_id="cid",
            client_secret="csec",
        )
        # Prime the cache as if a successful refresh already happened.
        auth._access_token = "cached-token"
        auth._expires_at = time.time() + 3600

        with patch(
            "authful_mcp_proxy.outbound_auth.httpx.AsyncClient"
        ) as mock_client_class:
            request = httpx.Request("GET", "https://upstream.example.com/")
            flow = auth.async_auth_flow(request)
            yielded = await flow.__anext__()

        assert yielded.headers["Authorization"] == "Bearer cached-token"
        mock_client_class.assert_not_called()

    @pytest.mark.asyncio
    async def test_expired_token_triggers_refresh(self):
        auth = OAuthClientCredentialsAuth(
            token_url="https://idp.example.com/token",
            client_id="cid",
            client_secret="csec",
        )
        # Prime the cache with a token that's "expired" considering the skew.
        auth._access_token = "stale-token"
        auth._expires_at = time.time() + 30  # less than _expiry_skew_seconds

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "access_token": "fresh-token",
            "expires_in": 3600,
        }

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_response

        with patch(
            "authful_mcp_proxy.outbound_auth.httpx.AsyncClient",
            return_value=mock_client,
        ):
            request = httpx.Request("GET", "https://upstream.example.com/")
            flow = auth.async_auth_flow(request)
            yielded = await flow.__anext__()

        assert yielded.headers["Authorization"] == "Bearer fresh-token"
        assert auth._access_token == "fresh-token"

    @pytest.mark.asyncio
    async def test_response_without_expires_in_treated_as_long_lived(self):
        auth = OAuthClientCredentialsAuth(
            token_url="https://idp.example.com/token",
            client_id="cid",
            client_secret="csec",
        )

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"access_token": "long-lived"}

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_response

        with patch(
            "authful_mcp_proxy.outbound_auth.httpx.AsyncClient",
            return_value=mock_client,
        ):
            request = httpx.Request("GET", "https://upstream.example.com/")
            flow = auth.async_auth_flow(request)
            await flow.__anext__()

        assert auth._expires_at is None
        assert auth._is_token_valid()

    @pytest.mark.asyncio
    async def test_scope_is_included_when_set(self):
        auth = OAuthClientCredentialsAuth(
            token_url="https://idp.example.com/token",
            client_id="cid",
            client_secret="csec",
            scope="upstream:read upstream:write",
        )

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"access_token": "t", "expires_in": 3600}

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post.return_value = mock_response

        with patch(
            "authful_mcp_proxy.outbound_auth.httpx.AsyncClient",
            return_value=mock_client,
        ):
            request = httpx.Request("GET", "https://upstream.example.com/")
            flow = auth.async_auth_flow(request)
            await flow.__anext__()

        assert (
            mock_client.post.call_args.kwargs["data"]["scope"]
            == "upstream:read upstream:write"
        )
