"""
MCP proxy with two operating modes selected by config type.

- :class:`DesktopConfig` -> stdio transport. The proxy is launched as a
  local process by the MCP client (Claude Desktop, Claude Code via
  ``claude mcp add --transport stdio``, Cursor, Codex, etc.). The
  proxy itself runs the OAuth Authorization Code + PKCE flow against an
  external OIDC IdP via :class:`ExternalOIDCAuth`, caches tokens on
  disk, and forwards them as Bearer tokens to the upstream MCP server.
  No inbound auth (local trust).
- :class:`WebConfig` -> http transport. The proxy runs as a standalone
  HTTP server that MCP clients connect to by URL (e.g. Claude Code via
  ``claude mcp add --transport http <name> <url>``). The proxy is an
  OAuth server in front of an external IdP (built by
  :func:`build_inbound_auth`); downstream MCP clients authenticate
  against the proxy and the proxy authenticates outbound to the upstream
  MCP server using the mechanism returned by
  :func:`build_outbound_auth`.

Both paths converge on FastMCP's ``create_proxy`` + per-session
``client.new()`` model so each downstream session gets an isolated
upstream connection.
"""

from typing import Any

from fastmcp import Client
from fastmcp.server import create_proxy

from .config import DesktopConfig, ProxyConfig, WebConfig
from .external_oidc import ExternalOIDCAuth
from .inbound_auth import build_inbound_auth
from .outbound_auth import build_outbound_auth


async def run_async(
    upstream_url: str,
    config: ProxyConfig,
    show_banner: bool = True,
    **transport_kwargs: Any,
) -> None:
    """Run the MCP proxy server.

    The transport (stdio vs http) is derived from the config type -- there
    is no separate transport argument. ``DesktopConfig`` always runs over
    stdio; ``WebConfig`` always runs over http.

    Args:
        upstream_url: URL of the upstream MCP server to proxy.
        config: Either a ``DesktopConfig`` (stdio mode) or a ``WebConfig``
            (http mode). Selects the auth strategy and transport.
        show_banner: Whether to display the server startup banner.
        **transport_kwargs: Additional keyword arguments passed to the
            transport layer. For stdio: ``log_level``. For http: ``host``,
            ``port``, ``log_level``, ``path``, ``uvicorn_config``.

    Raises:
        TypeError: If ``config`` is not a recognized ``ProxyConfig`` type.
    """
    if isinstance(config, DesktopConfig):
        await _run_desktop(upstream_url, config, show_banner, **transport_kwargs)
    elif isinstance(config, WebConfig):
        await _run_web(upstream_url, config, show_banner, **transport_kwargs)
    else:
        raise TypeError(
            f"Unsupported config type: {type(config).__name__}. "
            "Expected DesktopConfig or WebConfig."
        )


async def _run_desktop(
    upstream_url: str,
    config: DesktopConfig,
    show_banner: bool,
    **transport_kwargs: Any,
) -> None:
    """Run the proxy in stdio mode against an external OIDC IdP."""
    auth = ExternalOIDCAuth(
        issuer_url=config.issuer_url,
        client_id=config.client_id,
        client_secret=config.client_secret,
        scopes=config.scopes,
        redirect_url=config.redirect_url,
    )

    # Connect once to relay upstream server identity (name/version/icons/etc.)
    # so the proxy appears transparent to the MCP client.
    async with Client(transport=upstream_url, auth=auth) as authenticated_client:
        proxy_kwargs = _relay_server_info(authenticated_client)

    # Disconnected client; FastMCP calls client.new() per session.
    proxy_client = Client(transport=upstream_url, auth=auth)
    mcp_proxy = create_proxy(proxy_client, **proxy_kwargs)

    await mcp_proxy.run_async(
        transport="stdio", show_banner=show_banner, **transport_kwargs
    )


async def _run_web(
    upstream_url: str,
    config: WebConfig,
    show_banner: bool,
    **transport_kwargs: Any,
) -> None:
    """Run the proxy in http mode with FastMCP inbound auth + configurable outbound."""
    inbound_auth = build_inbound_auth(config)
    outbound_auth = build_outbound_auth(config)

    # Server-identity relay (the stdio path's pre-flight initialize handshake
    # against the upstream) is skipped in web mode: with outbound_auth='forward'
    # there is no inbound session yet, and with the other modes the proxy-owned
    # credential may or may not be authorized to call initialize. Operators who
    # want the proxy to appear transparent set proxy_name / proxy_version /
    # etc. on the config; without them FastMCP falls back to its auto-generated
    # FastMCPProxy-xxxx name.
    proxy_kwargs = _server_identity_kwargs(config)
    proxy_client = Client(transport=upstream_url, auth=outbound_auth)
    mcp_proxy = create_proxy(proxy_client, auth=inbound_auth, **proxy_kwargs)

    await mcp_proxy.run_async(
        transport="http", show_banner=show_banner, **transport_kwargs
    )


def _server_identity_kwargs(config: WebConfig) -> dict[str, Any]:
    """Collect operator-configured server-identity fields as create_proxy kwargs.

    Only includes fields the operator actually set. Unset fields are omitted so
    FastMCP's defaults apply.
    """
    kwargs: dict[str, Any] = {}
    if config.proxy_name:
        kwargs["name"] = config.proxy_name
    if config.proxy_version:
        kwargs["version"] = config.proxy_version
    if config.proxy_instructions:
        kwargs["instructions"] = config.proxy_instructions
    if config.proxy_website_url:
        kwargs["website_url"] = config.proxy_website_url
    return kwargs


def _relay_server_info(client: Client) -> dict[str, Any]:
    """Extract the upstream MCP server's identity so the proxy appears transparent.

    Reads name/version/website_url/icons from ``serverInfo`` (shown in the
    Claude Desktop connector list) and ``instructions`` (influences how the
    LLM selects and uses the server's tools).
    """
    proxy_kwargs: dict[str, Any] = {}
    init = client.initialize_result
    if init is None:
        return proxy_kwargs

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

    return proxy_kwargs
