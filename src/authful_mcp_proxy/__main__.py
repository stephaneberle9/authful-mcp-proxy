"""
Authful MCP Proxy - Command-line interface.

This module provides the CLI entry point for running the MCP proxy server. It:

- Parses command-line arguments and environment variables
- Configures OIDC authentication parameters
- Launches the proxy server with appropriate settings
- Handles graceful shutdown and error reporting

The CLI supports configuration via both command-line options (--oidc-*) and
environment variables (OIDC_*), with CLI arguments taking precedence.
"""

import argparse
import asyncio
import logging
import os
import sys

from . import __version__, mcp_proxy
from .config import OIDCConfig

logger = logging.getLogger(__name__)


def cli():
    """
    Parse command line arguments and merge with environment variables.

    Parses CLI arguments for OIDC configuration, backend URL, and logging options.
    Falls back to environment variables when CLI arguments are not provided, with
    CLI arguments taking precedence.

    Returns:
        Namespace: Parsed arguments with all configuration options.
    """
    parser = argparse.ArgumentParser(
        description=f"Authful Remote-HTTP-to-Local-stdio MCP Proxy (version {__version__})"
    )

    # Proxy server arguments
    parser.add_argument(
        "mcp_backend_url",
        metavar="MCP_BACKEND_URL",
        nargs="?",
        help="URL of remote backend MCP server to be proxied (can also be set via MCP_BACKEND_URL env var)",
    )

    parser.add_argument(
        "--no-banner",
        action="store_true",
        help="Don't show the proxy server banner",
    )

    # OIDC options
    parser.add_argument(
        "--oidc-issuer-url",
        help="OIDC issuer URL (can also be set via OIDC_ISSUER_URL env var)",
    )
    parser.add_argument(
        "--oidc-client-id",
        help="OAuth client ID (can also be set via OIDC_CLIENT_ID env var)",
    )
    parser.add_argument(
        "--oidc-client-secret",
        help="OAuth client secret (can also be set via OIDC_CLIENT_SECRET env var, optional for public OIDC clients that don't require any such)",
    )
    parser.add_argument(
        "--oidc-scopes",
        help="Space-separated OAuth scopes (can also be set via OIDC_SCOPES env var, default: 'openid profile email')",
    )
    parser.add_argument(
        "--oidc-redirect-url",
        help="Localhost URL for OAuth redirect (can also be set via OIDC_REDIRECT_URL env var, default: http://localhost:8080/auth/callback)",
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

    # Fallback to environment variables (CLI args take precedence)
    if not args.mcp_backend_url:
        args.mcp_backend_url = os.getenv("MCP_BACKEND_URL")
    if not args.oidc_issuer_url:
        args.oidc_issuer_url = os.getenv("OIDC_ISSUER_URL")
    if not args.oidc_client_id:
        args.oidc_client_id = os.getenv("OIDC_CLIENT_ID")
    if not args.oidc_client_secret:
        args.oidc_client_secret = os.getenv("OIDC_CLIENT_SECRET")
    if not args.oidc_scopes:
        args.oidc_scopes = os.getenv("OIDC_SCOPES")
    if not args.oidc_redirect_url:
        args.oidc_redirect_url = os.getenv("OIDC_REDIRECT_URL")
    if not args.debug:
        args.debug = os.getenv("MCP_PROXY_DEBUG", "").lower() in (
            "1",
            "true",
            "yes",
            "on",
        )

    return args


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


def main():
    """
    Main entry point for the Authful MCP Proxy application.

    Parses configuration, creates the OIDC config object, and launches the proxy server.
    Handles graceful shutdown and provides appropriate error messages for different
    exception types.

    Exits with status code 1 on errors, 0 on successful completion.
    """
    args = cli()

    try:
        # Create OIDC config
        oidc_config = OIDCConfig(
            issuer_url=args.oidc_issuer_url,
            client_id=args.oidc_client_id,
            client_secret=args.oidc_client_secret,
            scopes=args.oidc_scopes,
            redirect_url=args.oidc_redirect_url,
        )

        # Start the MCP proxy
        asyncio.run(
            mcp_proxy.run_async(
                backend_url=args.mcp_backend_url,
                oidc_config=oidc_config,
                show_banner=not args.no_banner,
                log_level=get_log_level_name(args),
            )
        )
    except KeyboardInterrupt:
        # Graceful shutdown, suppress noisy logs resulting from asyncio.run task cancellation propagation
        pass
    except ValueError as e:
        # Configuration error, log w/o stack trace
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except RuntimeError as e:
        # Runtime error, log w/o stack trace
        logger.error(f"Runtime error: {e}")
        sys.exit(1)
    except Exception as e:
        # Unexpected internal error, include full stack trace
        logger.error(f"Internal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
