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

import httpx
from exceptiongroup import BaseExceptionGroup
from mcp.shared.exceptions import McpError

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


class _LowercaseLevelFormatter(logging.Formatter):
    """Formatter that lowercases the level name to match Claude Desktop log style."""

    def format(self, record):
        record.levelname = record.levelname.lower()
        return super().format(record)


def configure_logging(args):
    """Configure logging based on command line arguments."""
    if args.silent:
        log_level = logging.ERROR
    elif args.debug:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO

    # Redirect logging to stderr (stdio transport reserves stdout for MCP JSON-RPC traffic)
    handler = logging.StreamHandler(sys.stderr)
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

    Parses configuration, creates the OIDC config object, and launches the proxy server.
    Handles graceful shutdown and provides appropriate error messages for different
    exception types.

    Exits with status code 1 on errors, 0 on successful completion.
    """
    args = cli()
    configure_logging(args)

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
    except Exception as e:
        # Catch-all for any exceptions (BaseExceptionGroup, KeyboardInterrupt, etc.)
        # All exception handling logic is in log_error_and_exit
        log_error_and_exit(e)
    finally:
        logging.shutdown()


if __name__ == "__main__":
    main()
