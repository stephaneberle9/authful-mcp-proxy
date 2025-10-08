"""
OIDC Auth client provider for external OpenID Connect (OIDC) providers.

This module provides an OAuth client for external OIDC providers (Keycloak, Auth0,
Okta, etc.) that handles the complete OAuth 2.0 authorization code flow with PKCE
using static client credentials. Key features include:

- Automatic provider configuration discovery via /.well-known/openid-configuration
- Browser-based user authentication with automatic OAuth callback handling
- Secure token exchange using PKCE (Proof Key for Code Exchange)
- Local token caching to eliminate repeated browser authentication
- Automatic access token refresh using refresh tokens
- Support for custom scopes and redirect URLs

Unlike dynamic client registration, this uses pre-configured client credentials
(client_id/client_secret) that must be set up in the OIDC provider beforehand.
"""

from __future__ import annotations

import asyncio
import secrets
import time
import webbrowser
from asyncio import Future
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

import anyio
import httpx
from fastmcp.client.auth.oauth import FileTokenStorage
from fastmcp.client.oauth_callback import create_oauth_callback_server
from fastmcp.server.auth.oidc_proxy import OIDCConfiguration
from fastmcp.utilities.logging import get_logger
from mcp.client.auth import PKCEParameters
from mcp.shared.auth import OAuthToken
from pydantic import AnyHttpUrl
from uvicorn.server import Server

__all__ = ["ExternalOIDCAuth"]

logger = get_logger(__name__)

HTTPX_REQUEST_TIMEOUT_SECONDS = 5
BROWSER_LOGIN_TIMEOUT_SECONDS = 300


@dataclass
class OIDCContext:
    """OIDC OAuth flow context - similar to OAuthContext but for external OIDC providers."""

    issuer_url: str
    client_id: str
    client_secret: str | None
    scopes: list[str]
    redirect_uri: str
    storage: FileTokenStorage

    # Discovered metadata
    oidc_config: OIDCConfiguration

    # Token management
    current_tokens: OAuthToken | None = None
    token_expiry_time: float | None = None

    # State
    lock: anyio.Lock = field(default_factory=anyio.Lock)

    def get_redirect_port(self) -> int:
        """Extract the port number from the redirect URI."""
        parsed = urlparse(self.redirect_uri)
        return parsed.port or 80

    def get_authorization_url(self, state: str, pkce: PKCEParameters) -> str:
        """Build the authorization URL with PKCE parameters."""
        auth_params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(self.scopes),
            "state": state,
            "code_challenge": pkce.code_challenge,
            "code_challenge_method": "S256",
        }
        return f"{self.oidc_config.authorization_endpoint}?{urlencode(auth_params)}"

    def get_token_exchange_data(
        self, auth_code: str, pkce: PKCEParameters
    ) -> dict[str, str]:
        """Build token exchange request data."""
        token_data = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "code_verifier": pkce.code_verifier,
        }
        if self.client_secret:
            token_data["client_secret"] = self.client_secret
        return token_data

    def get_token_refresh_data(self) -> dict[str, str]:
        """Build token refresh request data."""
        token_data = {
            "grant_type": "refresh_token",
            "refresh_token": self.current_tokens.refresh_token,
            "client_id": self.client_id,
        }
        if self.client_secret:
            token_data["client_secret"] = self.client_secret
        return token_data

    def update_token_expiry(self, token: OAuthToken) -> None:
        """Update token expiry time."""
        if token.expires_in:
            self.token_expiry_time = time.time() + token.expires_in
        else:
            self.token_expiry_time = None

    def is_token_valid(self) -> bool:
        """Check if current token is valid and not expired."""
        return bool(
            self.current_tokens
            and self.current_tokens.access_token
            and (
                not self.token_expiry_time or time.time() < self.token_expiry_time - 60
            )
        )

    def can_refresh_token(self) -> bool:
        """Check if token can be refreshed."""
        return bool(self.current_tokens and self.current_tokens.refresh_token)

    def clear_tokens(self) -> None:
        """Clear current tokens."""
        self.current_tokens = None
        self.token_expiry_time = None


class ExternalOIDCAuth(httpx.Auth):
    """
    OAuth client provider that authenticates against external OIDC providers.

    This client fetches OAuth configuration from an external OIDC provider's
    /.well-known/openid-configuration endpoint and uses static client credentials
    (client_id and client_secret) instead of dynamic client registration.

    Key differences from standard OAuth client:
    - Fetches config from issuer's /.well-known/openid-configuration (not MCP server)
    - Uses static client_id/client_secret (no dynamic registration)
    - Works with any OIDC-compliant provider (Keycloak, Auth0, Okta, etc.)

    Example:
        ```python
        from fastmcp.client import Client
        from fastmcp.client.auth import OIDCAuth

        auth = OIDCAuth(
            issuer_url="https://your-keycloak.example.com/realms/myrealm",
            client_id="your-client-id",
            client_secret="your-client-secret",
            scopes=["openid", "profile", "email"],
            redirect_url="http://localhost:8080/auth/callback"
        )

        async with Client("http://localhost:8000/mcp", auth=auth) as client:
            # Use authenticated client
            result = await client.call_tool("my_tool", {"arg": "value"})
        ```
    """

    def __init__(
        self,
        issuer_url: str,
        client_id: str,
        client_secret: str | None = None,
        scopes: str | list[str] | None = None,
        token_storage_cache_dir: Path | None = None,
        redirect_url: str | None = None,
    ):
        """
        Initialize OIDC Auth client provider.

        Args:
            issuer_url: OIDC issuer URL (e.g., "https://keycloak.example.com/realms/myrealm")
            client_id: Static OAuth client ID
            client_secret: Static OAuth client secret (optional for public OIDC clients that don't require any such)
            scopes: OAuth scopes to request (default: ["openid"]). Can be a
            space-separated string or a list of strings.
            token_storage_cache_dir: Directory for token storage (cache)
            redirect_url: Localhost URL for OAuth redirect (default: http://localhost:8080/auth/callback)
        """
        # Validate required parameters
        if not issuer_url:
            raise ValueError("Missing required issuer URL")
        if not client_id:
            raise ValueError("Missing required client id")

        # Parse and validate scopes
        if isinstance(scopes, list):
            scopes_list = scopes
        elif scopes is not None:
            scopes_list = scopes.split()
        else:
            scopes_list = ["openid"]

        # Ensure openid scope is always included
        if "openid" not in scopes_list:
            scopes_list.insert(0, "openid")

        # Setup redirect port and redirect URI
        redirect_uri = redirect_url or "http://localhost:8080/auth/callback"

        # Initialize token storage - reuse FileTokenStorage
        storage = FileTokenStorage(
            server_url=issuer_url, cache_dir=token_storage_cache_dir
        )

        # Fetch OIDC configuration
        config_url = f"{issuer_url.rstrip('/')}/.well-known/openid-configuration"
        oidc_config = OIDCConfiguration.get_oidc_configuration(
            AnyHttpUrl(config_url),
            strict=True,
            timeout_seconds=HTTPX_REQUEST_TIMEOUT_SECONDS,
        )

        # Validate required endpoints
        if not oidc_config.authorization_endpoint:
            raise ValueError("OIDC configuration missing authorization_endpoint")
        if not oidc_config.token_endpoint:
            raise ValueError("OIDC configuration missing token_endpoint")

        # Create context with all configuration and state
        self.context = OIDCContext(
            issuer_url=issuer_url,
            client_id=client_id,
            client_secret=client_secret,
            scopes=scopes_list,
            redirect_uri=redirect_uri,
            oidc_config=oidc_config,
            storage=storage,
        )

        self._initialized = False

    async def _initialize(self) -> None:
        """Load stored tokens if available."""
        if self._initialized:
            return

        self.context.current_tokens = await self.context.storage.get_tokens()
        if self.context.current_tokens:
            self.context.update_token_expiry(self.context.current_tokens)
        self._initialized = True
        logger.debug("OIDC Auth client initialized")

    async def _run_callback_server(self) -> tuple[str, str]:
        """Handle OAuth callback and return (auth_code, state)."""
        # Create a future to capture the OAuth response
        response_future: Future[Any] = asyncio.get_running_loop().create_future()

        # Create server with the future
        server: Server = create_oauth_callback_server(
            port=self.context.get_redirect_port(),
            server_url=self.context.issuer_url,
            response_future=response_future,
        )

        # Run server until response is received with timeout logic
        async with anyio.create_task_group() as tg:
            tg.start_soon(server.serve)
            logger.info(
                f"🎧 OIDC Auth callback server started on {self.context.redirect_uri}"
            )

            try:
                with anyio.fail_after(BROWSER_LOGIN_TIMEOUT_SECONDS):
                    auth_code, state = await response_future
                    return auth_code, state
            except TimeoutError:
                raise TimeoutError(
                    f"OIDC Auth callback timed out after {BROWSER_LOGIN_TIMEOUT_SECONDS} seconds"
                )
            finally:
                server.should_exit = True
                await asyncio.sleep(0.1)  # Allow server to shut down gracefully
                tg.cancel_scope.cancel()

        raise RuntimeError("OIDC Auth callback handler could not be started")

    async def _perform_auth_flow(self) -> OAuthToken:
        """Perform the OAuth authorization code flow with PKCE."""
        async with self.context.lock:
            # Generate PKCE parameters and state
            pkce = PKCEParameters.generate()
            state = secrets.token_urlsafe(32)

            # Build authorization URL using context method
            authorization_url = self.context.get_authorization_url(state, pkce)

            # Open browser for authorization
            logger.info(f"Opening browser for OIDC authorization: {authorization_url}")
            webbrowser.open(authorization_url)

            # Wait for callback
            auth_code, returned_state = await self._run_callback_server()

            # Validate state
            if returned_state is None or not secrets.compare_digest(
                returned_state, state
            ):
                raise RuntimeError(
                    f"OAuth state mismatch: {returned_state} != {state} - possible CSRF attack"
                )

            # Validate auth code
            if not auth_code:
                raise RuntimeError("No authorization code received")

            # Build token data using context method
            token_data = self.context.get_token_exchange_data(auth_code, pkce)

            # Exchange authorization code for tokens
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    str(self.context.oidc_config.token_endpoint),
                    data=token_data,
                    timeout=float(HTTPX_REQUEST_TIMEOUT_SECONDS),
                )
                response.raise_for_status()
                token_response = response.json()

            # Parse and store tokens
            tokens = OAuthToken.model_validate(token_response)
            await self.context.storage.set_tokens(tokens)
            self.context.current_tokens = tokens
            self.context.update_token_expiry(tokens)

            logger.info("OIDC Auth flow completed successfully")
            return tokens

    async def _refresh_tokens(self) -> OAuthToken:
        """Refresh access token using refresh token."""
        async with self.context.lock:
            if not self.context.can_refresh_token():
                raise RuntimeError("No refresh token available")

            token_data = self.context.get_token_refresh_data()

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    str(self.context.oidc_config.token_endpoint),
                    data=token_data,
                    timeout=float(HTTPX_REQUEST_TIMEOUT_SECONDS),
                )
                response.raise_for_status()
                token_response = response.json()

            # Parse and store new tokens
            tokens = OAuthToken.model_validate(token_response)
            await self.context.storage.set_tokens(tokens)
            self.context.current_tokens = tokens
            self.context.update_token_expiry(tokens)

            logger.debug("OIDC Auth tokens refreshed")
            return tokens

    async def _get_token(self) -> str:
        """
        Get a valid access token, renewing it if necessary.

        Returns:
            A valid access token, either from cache or after renewal.
        """
        await self._initialize()

        # If token is valid, return it
        if self.context.is_token_valid():
            return self.context.current_tokens.access_token

        # Token expired or missing - refresh or re-auth
        return await self._renew_token()

    async def _renew_token(self) -> str:
        """Handle authentication errors by refreshing or re-authenticating."""
        if self.context.can_refresh_token():
            try:
                await self._refresh_tokens()
                logger.debug("Token refreshed successfully")
            except Exception as e:
                logger.warning(f"Token refresh failed: {e}, performing full auth flow")
                await self._perform_auth_flow()
        else:
            logger.debug("No refresh token available, performing full auth flow")
            await self._perform_auth_flow()

        return self.context.current_tokens.access_token

    async def async_auth_flow(
        self, request: httpx.Request
    ) -> AsyncGenerator[httpx.Request, httpx.Response]:
        """
        HTTPX auth flow implementation.

        This method is compatible with httpx.Auth interface and automatically
        adds the Bearer token to requests.
        """
        # Get current access token or a new one if it has expired
        access_token = await self._get_token()

        # Add authorization header
        request.headers["Authorization"] = f"Bearer {access_token}"

        # Yield request and handle response
        response = yield request

        # If we get 401, handle auth error and retry
        if response.status_code == 401:
            logger.debug("Received 401, attempting token refresh")
            try:
                # Token invalid or missing - refresh or re-auth
                access_token = await self._renew_token()

                # Update request with new token
                request.headers["Authorization"] = f"Bearer {access_token}"

                # Retry request
                response = yield request
            except Exception as e:
                logger.error(f"Token refresh and retry failed: {e}")
                # Return original 401 response
                pass
