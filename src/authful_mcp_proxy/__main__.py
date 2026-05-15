"""
Authful MCP Proxy - Command-line interface.

This module provides the CLI entry point for running the MCP proxy server. It:

- Parses command-line arguments and environment variables
- Builds either a ``DesktopConfig`` (stdio transport) or a ``WebConfig``
  (http transport) based on ``--transport``
- Launches the proxy server with appropriate settings
- Handles graceful shutdown and error reporting

CLI flags fall back to matching environment variables (CLI arguments take
precedence). For stdio mode the ``OIDC_*`` env vars apply; for http mode
the inbound provider params (``OIDC_*``, ``COGNITO_*``, ``AZURE_*``,
``--audience``, ``--base-url``) and the outbound mode params
(``OUTBOUND_*``) apply.
"""

import argparse
import asyncio
import logging
import os
import sys

import httpx
from exceptiongroup import BaseExceptionGroup
from mcp.shared.exceptions import McpError

from . import __version__, mcp_proxy
from .config import DesktopConfig, ProxyConfig, WebConfig

logger = logging.getLogger(__name__)


_AUTH_PROVIDERS = ("oidc", "keycloak", "aws-cognito", "google", "azure")
_OUTBOUND_AUTH_MODES = ("forward", "oauth-client-credentials", "static")


def cli() -> argparse.Namespace:
    """
    Parse command line arguments and merge with environment variables.

    Parses CLI arguments for OIDC configuration, backend URL, and logging options.
    Falls back to environment variables when CLI arguments are not provided, with
    CLI arguments taking precedence.

    Returns:
        Namespace: Parsed arguments with all configuration options.
    """
    parser = argparse.ArgumentParser(
        description=(
            f"Authful MCP Proxy -- bridges remote MCP servers protected by "
            f"token validation or static credentials to MCP clients such as "
            f"Claude Desktop, Claude Code, Cursor, Windsurf, MCP Inspector, "
            f"and Claude.ai (version {__version__})"
        )
    )

    # Proxy server arguments
    parser.add_argument(
        "mcp_backend_url",
        metavar="MCP_BACKEND_URL",
        nargs="?",
        help="URL of remote backend MCP server to be proxied "
        "(can also be set via MCP_BACKEND_URL env var)",
    )
    parser.add_argument(
        "--no-banner",
        action="store_true",
        help="Don't show the proxy server banner",
    )

    # Transport options
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default=None,
        help="Transport to serve on. "
        "'stdio' (default): proxy is launched as a local process by the MCP "
        "client (Claude Desktop, Claude Code via 'claude mcp add --transport stdio', "
        "Cursor, Windsurf, etc.). "
        "'http': proxy runs as a standalone HTTP server that clients connect to by URL "
        "(e.g. Claude Code via 'claude mcp add --transport http <name> <url>'). "
        "Can also be set via MCP_TRANSPORT env var.",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Host address to bind to when using HTTP transport "
        "(can also be set via MCP_HOST env var, default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to listen on when using HTTP transport "
        "(can also be set via MCP_PORT env var, default: 8000)",
    )

    # Inbound OIDC options -- used by:
    # - stdio: the desktop OAuth client (issuer/client/scopes/redirect)
    # - http: the FastMCP inbound provider when --auth-provider is
    #   'oidc'/'keycloak' (issuer_url), or as the OAuth client_id/secret
    #   common across 'oidc'/'aws-cognito'/'google'/'azure' (unused for
    #   'keycloak' which is a RemoteAuthProvider).
    parser.add_argument(
        "--oidc-issuer-url",
        help="OIDC issuer / Keycloak realm URL "
        "(can also be set via OIDC_ISSUER_URL env var)",
    )
    parser.add_argument(
        "--oidc-client-id",
        help="OAuth client ID (can also be set via OIDC_CLIENT_ID env var)",
    )
    parser.add_argument(
        "--oidc-client-secret",
        help="OAuth client secret (can also be set via OIDC_CLIENT_SECRET env var, "
        "optional for public OIDC clients that don't require any such)",
    )
    parser.add_argument(
        "--oidc-scopes",
        help="Space-separated OAuth scopes "
        "(can also be set via OIDC_SCOPES env var, default for stdio: 'openid profile email')",
    )
    parser.add_argument(
        "--oidc-redirect-url",
        help="Localhost URL for OAuth redirect -- stdio mode only "
        "(can also be set via OIDC_REDIRECT_URL env var, "
        "default: http://localhost:8080/auth/callback)",
    )

    # Web-mode-only inbound options
    parser.add_argument(
        "--auth-provider",
        choices=list(_AUTH_PROVIDERS),
        default=None,
        help="Inbound auth provider for http mode. 'keycloak' uses FastMCP's "
        "KeycloakAuthProvider (RemoteAuthProvider -- Keycloak >= 26.6.0 with "
        "native DCR). 'oidc' uses OIDCProxy in DCR-bridge mode for any "
        "generic OIDC IdP (including older Keycloak). 'aws-cognito', "
        "'google', 'azure' use the matching IdP-specific FastMCP providers. "
        "Can also be set via AUTH_PROVIDER env var.",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Publicly reachable URL of the proxy -- required for http mode "
        "(can also be set via BASE_URL env var). Used by inbound providers to "
        "advertise their authorization/token/JWKS endpoints to downstream MCP "
        "clients via OAuth 2.0 protected-resource metadata.",
    )
    parser.add_argument(
        "--audience",
        default=None,
        help="JWT 'aud' claim to require on incoming tokens -- used by oidc and "
        "keycloak inbound providers "
        "(can also be set via AUDIENCE env var, recommended for production)",
    )
    parser.add_argument(
        "--cognito-user-pool-id",
        default=None,
        help="AWS Cognito user pool ID -- required for --auth-provider aws-cognito "
        "(can also be set via COGNITO_USER_POOL_ID env var)",
    )
    parser.add_argument(
        "--cognito-aws-region",
        default=None,
        help="AWS region for the Cognito user pool -- required for --auth-provider aws-cognito "
        "(can also be set via COGNITO_AWS_REGION env var)",
    )
    parser.add_argument(
        "--azure-tenant-id",
        default=None,
        help="Azure AD tenant ID -- required for --auth-provider azure "
        "(can also be set via AZURE_TENANT_ID env var)",
    )
    parser.add_argument(
        "--azure-identifier-uri",
        default=None,
        help="Azure Application ID URI used for scope prefixing -- optional for "
        "--auth-provider azure (can also be set via AZURE_IDENTIFIER_URI env var)",
    )

    # Web-mode-only outbound options
    parser.add_argument(
        "--outbound-auth",
        choices=list(_OUTBOUND_AUTH_MODES),
        default=None,
        help="How the proxy authenticates outbound calls to the upstream MCP "
        "server. 'forward' (default): reuse the downstream session's bearer "
        "token (Pattern C). 'oauth-client-credentials': proxy obtains its own "
        "token via OAuth client_credentials grant against an outbound IdP "
        "independent of the inbound IdP (Pattern B with a tenant- or user-"
        "scoped OAuth credential). 'static': proxy injects a fixed header "
        "value such as an API key, API token, or PAT (Pattern B with a "
        "tenant- or user-scoped static credential). "
        "Can also be set via OUTBOUND_AUTH env var.",
    )
    parser.add_argument(
        "--outbound-client-id",
        default=None,
        help="OAuth client ID for outbound oauth-client-credentials mode "
        "(can also be set via OUTBOUND_CLIENT_ID env var)",
    )
    parser.add_argument(
        "--outbound-client-secret",
        default=None,
        help="OAuth client secret for outbound oauth-client-credentials mode "
        "(can also be set via OUTBOUND_CLIENT_SECRET env var)",
    )
    parser.add_argument(
        "--outbound-token-url",
        default=None,
        help="Token endpoint URL for outbound oauth-client-credentials mode "
        "(can also be set via OUTBOUND_TOKEN_URL env var; independent of the "
        "inbound IdP -- in Pattern B the upstream's auth mechanism is by "
        "definition disconnected from the IdP that fronts the proxy)",
    )
    parser.add_argument(
        "--outbound-header-name",
        default=None,
        help="Header name for outbound static mode "
        "(can also be set via OUTBOUND_HEADER_NAME env var, default: Authorization)",
    )
    parser.add_argument(
        "--outbound-header-value",
        default=None,
        help="Literal header value for outbound static mode "
        "(can also be set via OUTBOUND_HEADER_VALUE env var; e.g. 'Bearer eyJ...' "
        "for a bearer token, or a bare API key paired with "
        "--outbound-header-name X-API-Key)",
    )

    # Logging options
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--silent", action="store_true", help="Show only error messages")
    group.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging (can also be set through 'MCP_PROXY_DEBUG' environment variable)",
    )

    args = parser.parse_args()

    # Env var fallbacks (CLI args win when present)
    _apply_env_fallbacks(args)

    return args


def _apply_env_fallbacks(args: argparse.Namespace) -> None:
    """Apply environment-variable fallbacks for any CLI args left unset.

    Walks a table of (attr, env_var) pairs and sets each unset attribute
    from its matching env var. Mode-specific defaulting (default transport,
    int-conversion for port, boolean parsing for MCP_PROXY_DEBUG) is
    handled separately below.
    """
    env_fallbacks = (
        ("mcp_backend_url", "MCP_BACKEND_URL"),
        ("host", "MCP_HOST"),
        ("oidc_issuer_url", "OIDC_ISSUER_URL"),
        ("oidc_client_id", "OIDC_CLIENT_ID"),
        ("oidc_client_secret", "OIDC_CLIENT_SECRET"),
        ("oidc_scopes", "OIDC_SCOPES"),
        ("oidc_redirect_url", "OIDC_REDIRECT_URL"),
        ("auth_provider", "AUTH_PROVIDER"),
        ("base_url", "BASE_URL"),
        ("audience", "AUDIENCE"),
        ("cognito_user_pool_id", "COGNITO_USER_POOL_ID"),
        ("cognito_aws_region", "COGNITO_AWS_REGION"),
        ("azure_tenant_id", "AZURE_TENANT_ID"),
        ("azure_identifier_uri", "AZURE_IDENTIFIER_URI"),
        ("outbound_auth", "OUTBOUND_AUTH"),
        ("outbound_client_id", "OUTBOUND_CLIENT_ID"),
        ("outbound_client_secret", "OUTBOUND_CLIENT_SECRET"),
        ("outbound_token_url", "OUTBOUND_TOKEN_URL"),
        ("outbound_header_name", "OUTBOUND_HEADER_NAME"),
        ("outbound_header_value", "OUTBOUND_HEADER_VALUE"),
    )
    for attr, env_name in env_fallbacks:
        if not getattr(args, attr):
            setattr(args, attr, os.getenv(env_name))

    if not args.transport:
        args.transport = os.getenv("MCP_TRANSPORT") or "stdio"
    if not args.port:
        port_env = os.getenv("MCP_PORT")
        args.port = int(port_env) if port_env else None
    if not args.debug:
        args.debug = os.getenv("MCP_PROXY_DEBUG", "").lower() in (
            "1",
            "true",
            "yes",
            "on",
        )


def build_proxy_config(args: argparse.Namespace) -> ProxyConfig:
    """Build the appropriate ProxyConfig from parsed CLI args.

    Branches on ``args.transport``:

    - ``stdio`` -> ``DesktopConfig`` using the ``--oidc-*`` flags.
    - ``http`` -> ``WebConfig`` using ``--auth-provider`` plus the relevant
      per-provider and outbound flags. Per-provider required-field
      validation lives in ``WebConfig.__post_init__``; missing transport-
      level fields (e.g. ``--base-url``) are caught here.

    Raises:
        ValueError: If required transport-level fields are missing.
    """
    if args.transport == "stdio":
        return DesktopConfig(
            issuer_url=args.oidc_issuer_url,
            client_id=args.oidc_client_id,
            client_secret=args.oidc_client_secret,
            scopes=args.oidc_scopes,
            redirect_url=args.oidc_redirect_url,
        )

    # http
    if not args.base_url:
        raise ValueError(
            "--base-url (or BASE_URL env var) is required for --transport http"
        )
    if not args.auth_provider:
        raise ValueError(
            "--auth-provider (or AUTH_PROVIDER env var) is required for "
            "--transport http"
        )

    return WebConfig(
        auth_provider=args.auth_provider,
        base_url=args.base_url,
        client_id=args.oidc_client_id,
        client_secret=args.oidc_client_secret,
        scopes=args.oidc_scopes,
        issuer_url=args.oidc_issuer_url,
        audience=args.audience,
        cognito_user_pool_id=args.cognito_user_pool_id,
        cognito_aws_region=args.cognito_aws_region,
        azure_tenant_id=args.azure_tenant_id,
        azure_identifier_uri=args.azure_identifier_uri,
        outbound_auth=args.outbound_auth or "forward",
        outbound_client_id=args.outbound_client_id,
        outbound_client_secret=args.outbound_client_secret,
        outbound_token_url=args.outbound_token_url,
        outbound_header_name=args.outbound_header_name or "Authorization",
        outbound_header_value=args.outbound_header_value,
    )


class _LowercaseLevelFormatter(logging.Formatter):
    """Formatter that lowercases the level name to match Claude Desktop log style."""

    def format(self, record):
        record.levelname = record.levelname.lower()
        return super().format(record)


def configure_logging(args):
    """Configure logging based on command line arguments.

    In stdio mode, stdout is reserved for MCP JSON-RPC traffic so logs are
    forced to stderr. In http mode, stdout is free; logs go to stdout there
    (more conventional for HTTP server output, especially in containers).
    """
    if args.silent:
        log_level = logging.ERROR
    elif args.debug:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO

    stream = sys.stderr if args.transport == "stdio" else sys.stdout
    handler = logging.StreamHandler(stream)
    handler.setFormatter(
        _LowercaseLevelFormatter(
            fmt="%(asctime)s.%(msecs)03dZ [%(name)s] [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    logging.root.addHandler(handler)
    logging.root.setLevel(log_level)


def get_log_level_name(args) -> str:
    """
    Determine the appropriate log level based on command line arguments.

    Args:
        args: Parsed command line arguments containing silent/debug flags.

    Returns:
        str: Log level name ('ERROR', 'DEBUG', or 'INFO').
    """
    if args.silent:
        return logging.getLevelName(logging.ERROR)
    elif args.debug:
        return logging.getLevelName(logging.DEBUG)
    else:
        return logging.getLevelName(logging.INFO)


def extract_root_cause(eg: BaseExceptionGroup) -> BaseException:
    """Extract the root cause from singly-nested exception groups.

    Exceptions from anyio task groups and asyncio often get wrapped in multiple
    layers of BaseExceptionGroup. This recursively unwraps to find the actual cause.
    """
    exceptions = eg.exceptions
    while len(exceptions) == 1 and isinstance(exceptions[0], BaseExceptionGroup):
        exceptions = exceptions[0].exceptions
    if len(exceptions) == 1:
        return exceptions[0]
    return eg


def log_error_and_exit(exc: BaseException) -> None:
    """Log an exception appropriately and exit with status 1.

    Provides clean error messages without stack traces for expected error types,
    and full tracebacks for unexpected internal errors. Recursively handles
    BaseExceptionGroup by extracting and processing the root cause.

    Args:
        exc: The exception to log and handle.
    """
    if isinstance(exc, KeyboardInterrupt):
        # Graceful shutdown - exit without logging
        return

    # Handle BaseExceptionGroup recursively
    if isinstance(exc, BaseExceptionGroup):
        cause = extract_root_cause(exc)
        if isinstance(cause, SystemExit):
            # SystemExit from uvicorn loses the original error message;
            # check __context__ for the real cause (e.g., OSError from port binding)
            context = getattr(cause, "__context__", None)
            log_error_and_exit(context if context else cause)
        else:
            log_error_and_exit(cause)
        return

    # Log based on exception type
    if isinstance(exc, httpx.HTTPStatusError | McpError):
        logger.error(f"Backend error: {exc}")
    elif isinstance(
        exc,
        httpx.ConnectError
        | httpx.ConnectTimeout
        | httpx.ReadTimeout
        | httpx.TimeoutException,
    ):
        logger.error(f"Network error: {exc}")
    elif isinstance(exc, OSError):
        logger.error(f"System error: {exc}")
    elif isinstance(exc, ValueError):
        logger.error(f"Configuration error: {exc}")
    elif isinstance(exc, RuntimeError):
        logger.error(f"Runtime error: {exc}")
    elif isinstance(exc, SystemExit):
        # Unexpected system exit without proper context
        logger.error(f"Unexpected system exit: {exc}")
        sys.exit(exc.code if exc.code is not None else 1)
    else:
        # Unexpected internal error - include full traceback for debugging
        logger.error(f"Internal error: {exc}", exc_info=exc)

    sys.exit(1)


def main():
    """
    Main entry point for the Authful MCP Proxy application.

    Parses configuration, builds the appropriate ProxyConfig (DesktopConfig for
    stdio mode, WebConfig for http mode), and launches the proxy server. Handles
    graceful shutdown and provides appropriate error messages for different
    exception types.

    Exits with status code 1 on errors, 0 on successful completion.
    """
    args = cli()
    configure_logging(args)

    try:
        config = build_proxy_config(args)

        # Build transport kwargs forwarded to FastMCP's run_async.
        # log_level applies to both transports; host/port apply to http only.
        transport_kwargs: dict = {"log_level": get_log_level_name(args)}
        if args.transport == "http":
            if args.host:
                transport_kwargs["host"] = args.host
            if args.port:
                transport_kwargs["port"] = args.port

        # Start the MCP proxy
        asyncio.run(
            mcp_proxy.run_async(
                backend_url=args.mcp_backend_url,
                config=config,
                show_banner=not args.no_banner,
                **transport_kwargs,
            )
        )
    except Exception as e:
        # Catch-all for any exceptions (BaseExceptionGroup, KeyboardInterrupt, etc.)
        # All exception handling logic is in log_error_and_exit
        log_error_and_exit(e)
    finally:
        logging.shutdown()


if __name__ == "__main__":
    main()
