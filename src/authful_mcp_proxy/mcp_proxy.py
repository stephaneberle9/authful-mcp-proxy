"""
OIDC OAuth-enabled MCP Proxy.

This module provides the main proxy server that bridges remote HTTP MCP servers
protected by token validation to local or remote MCP clients. It handles:

- OIDC authentication via external authorization servers
- Transport bridging (stdio for local clients, HTTP for remote web clients)
- Session management and token refresh
- Transparent request forwarding to the backend MCP server

The proxy uses ExternalOIDCAuth to obtain access tokens through the OAuth 2.0
authorization code flow and attaches them as Bearer tokens to all backend requests.
This enables MCP clients to connect to token-protected MCP servers without
implementing OIDC authentication themselves.

When running with stdio transport the proxy is launched as a local process by the MCP
client (Claude Desktop, Claude Code via `claude mcp add --transport stdio`, Cursor,
Windsurf, etc.). When running with http transport the proxy runs as a standalone HTTP
server and MCP clients connect to it by URL (e.g. Claude Code via
`claude mcp add --transport http <name> <url>`).
"""

from typing import Any

from fastmcp import Client
from fastmcp.server import create_proxy
from fastmcp.server.server import Transport

from .config import OIDCConfig
from .external_oidc import ExternalOIDCAuth


async def run_async(
    backend_url: str,
    oidc_config: OIDCConfig,
    transport: Transport = "stdio",
    show_banner: bool = True,
    **transport_kwargs: Any,
):
    """
    Run the MCP proxy server with OIDC authentication.

    Creates an authenticated connection to the backend MCP server using OIDC
    authentication, then proxies all requests through the chosen transport.

    Args:
        backend_url: URL of the remote backend MCP server to proxy.
        oidc_config: OIDC authentication configuration with issuer, client credentials,
                     and scopes.
        transport: Transport to serve on. "stdio" (default) — the proxy is launched as
                   a local process by the MCP client (Claude Desktop, Claude Code via
                   `claude mcp add --transport stdio`, Cursor, Windsurf, etc.).
                   "http" — the proxy runs as a standalone HTTP server that MCP clients
                   connect to by URL (e.g. Claude Code via
                   `claude mcp add --transport http <name> <url>`).
        show_banner: Whether to display the server startup banner (default: True).
        **transport_kwargs: Additional keyword arguments passed to the transport layer.
                           For stdio: log_level.
                           For http: host, port, log_level, path, uvicorn_config.

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
        # Relay backend server identity so the proxy appears transparent to MCP clients:
        # name/version/website_url/icons shown in Claude Desktop's connector list;
        # instructions influence how the LLM selects and uses the server's tools.
        proxy_kwargs: dict[str, Any] = {}
        if init := authenticated_client.initialize_result:
            if info := getattr(init, "serverInfo", None):
                if name := getattr(info, "name", None):
                    proxy_kwargs["name"] = name
                if version := getattr(info, "version", None):
                    proxy_kwargs["version"] = version
                if website_url := getattr(info, "websiteUrl", None):
                    proxy_kwargs["website_url"] = website_url
                if icons := getattr(info, "icons", None):
                    proxy_kwargs["icons"] = icons
            if instructions := getattr(init, "instructions", None):
                proxy_kwargs["instructions"] = instructions

    # Pass a disconnected client to create_proxy. FastMCP will call client.new() per
    # incoming MCP session, giving each session its own backend connection and preventing
    # context mixing. For stdio there is only ever one session; for HTTP each connecting
    # client gets an isolated backend session.
    proxy_client = Client(transport=backend_url, auth=auth)
    mcp_proxy = create_proxy(proxy_client, **proxy_kwargs)

    await mcp_proxy.run_async(
        transport=transport, show_banner=show_banner, **transport_kwargs
    )
