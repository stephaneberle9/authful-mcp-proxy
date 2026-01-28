"""
OIDC OAuth-enabled MCP Proxy with stdio transport.

This module provides the main proxy server that bridges remote HTTP MCP servers
protected by token validation to local stdio transport for MCP clients like Claude
Desktop. It handles:

- OIDC authentication via external authorization servers
- HTTP-to-stdio transport bridging
- Session management and token refresh
- Transparent request forwarding to the backend MCP server

The proxy uses ExternalOIDCAuth to obtain access tokens through the OAuth 2.0
authorization code flow and attaches them as Bearer tokens to all backend requests.
This enables MCP clients to connect to token-protected MCP servers without
implementing OIDC authentication themselves.
"""

from typing import Any

from fastmcp import Client
from fastmcp.server import FastMCP

from .config import OIDCConfig
from .external_oidc import ExternalOIDCAuth


async def run_async(
    backend_url: str,
    oidc_config: OIDCConfig,
    show_banner: bool = True,
    **transport_kwargs: Any,
):
    """
    Run the MCP proxy server with OIDC authentication.

    Creates an authenticated connection to the backend MCP server using OIDC
    authentication, then proxies all requests through stdio transport for
    local MCP clients.

    Args:
        backend_url: URL of the remote backend MCP server to proxy.
        oidc_config: OIDC authentication configuration with issuer, client credentials,
                     and scopes.
        show_banner: Whether to display the server startup banner (default: True).
        **transport_kwargs: Additional keyword arguments passed to the transport layer
                           (e.g., log_level).

    Raises:
        ValueError: If required OIDC parameters (issuer_url, client_id) are missing.
        RuntimeError: If authentication or connection to backend server fails.
    """
    # Create OIDC auth provider
    auth = ExternalOIDCAuth(
        issuer_url=oidc_config.issuer_url,
        client_id=oidc_config.client_id,
        client_secret=oidc_config.client_secret,
        scopes=oidc_config.scopes,
        redirect_url=oidc_config.redirect_url,
    )

    # Create a client that authenticates (once) with the configured OIDC auth provider
    # and connects to the backend MCP server
    async with Client(transport=backend_url, auth=auth) as authenticated_client:
        # Get server info from the authenticated client to relay it accurately
        # If the client is connected, initialize_result will be populated
        init_result = authenticated_client.initialize_result
        server_info = getattr(init_result, "serverInfo", None)

        # Extract only properties supported by FastMCP.__init__
        proxy_kwargs = {}
        if server_info:
            proxy_kwargs["name"] = getattr(server_info, "name", None)
            proxy_kwargs["version"] = getattr(server_info, "version", None)
            # Map camelCase from MCP to snake_case for FastMCP
            proxy_kwargs["website_url"] = getattr(server_info, "websiteUrl", None)
            proxy_kwargs["icons"] = getattr(server_info, "icons", None)

        if init_result:
            # Only relay instructions if they are set
            instructions = getattr(init_result, "instructions", None)
            if instructions:
                proxy_kwargs["instructions"] = instructions

        # Create FastMCP proxy server that reuses the connected session for all requests
        # Warning: Sharing the same backend session for all requests may cause context mixing
        # and race conditions in concurrent scenarios. When running this MCP proxy with stdio
        # transport inside MCP clients like Claude Desktop this is generally not the case.
        mcp_proxy = FastMCP.as_proxy(
            backend=authenticated_client,
            **proxy_kwargs,
        )

        # Run via stdio for MCP clients like Claude Desktop
        await mcp_proxy.run_async(
            transport="stdio", show_banner=show_banner, **transport_kwargs
        )
