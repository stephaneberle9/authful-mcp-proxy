"""Tests for authful_mcp_proxy.__main__ module."""

import logging
import os
from unittest.mock import patch

from authful_mcp_proxy.__main__ import cli, get_log_level_name


class TestCLI:
    """Test CLI argument parsing."""

    def test_cli_with_all_args(self):
        """Test CLI parsing with all arguments provided."""
        test_args = [
            "http://backend.example.com/mcp",
            "--oidc-issuer-url",
            "https://auth.example.com",
            "--oidc-client-id",
            "test-client",
            "--oidc-client-secret",
            "test-secret",
            "--oidc-scopes",
            "openid profile",
            "--oidc-redirect-url",
            "http://localhost:8080/callback",
            "--debug",
        ]

        with patch("sys.argv", ["authful-mcp-proxy"] + test_args):
            args = cli()

        assert args.mcp_backend_url == "http://backend.example.com/mcp"
        assert args.oidc_issuer_url == "https://auth.example.com"
        assert args.oidc_client_id == "test-client"
        assert args.oidc_client_secret == "test-secret"
        assert args.oidc_scopes == "openid profile"
        assert args.oidc_redirect_url == "http://localhost:8080/callback"
        assert args.debug is True
        assert args.silent is False

    def test_cli_with_minimal_args(self):
        """Test CLI parsing with minimal arguments."""
        test_args = ["http://backend.example.com/mcp"]

        with patch("sys.argv", ["authful-mcp-proxy"] + test_args):
            args = cli()

        assert args.mcp_backend_url == "http://backend.example.com/mcp"
        assert args.debug is False
        assert args.silent is False

    def test_cli_with_no_backend_url(self):
        """Test CLI parsing when backend URL is not provided."""
        with patch("sys.argv", ["authful-mcp-proxy"]):
            with patch.dict(os.environ, {}, clear=True):
                args = cli()

        assert args.mcp_backend_url is None

    def test_cli_env_var_fallback(self):
        """Test that CLI falls back to environment variables."""
        env_vars = {
            "MCP_BACKEND_URL": "http://env-backend.example.com/mcp",
            "OIDC_ISSUER_URL": "https://env-auth.example.com",
            "OIDC_CLIENT_ID": "env-client",
            "OIDC_CLIENT_SECRET": "env-secret",
            "OIDC_SCOPES": "openid email",
            "OIDC_REDIRECT_URL": "http://localhost:9090/callback",
        }

        with patch("sys.argv", ["authful-mcp-proxy"]):
            with patch.dict(os.environ, env_vars):
                args = cli()

        assert args.mcp_backend_url == "http://env-backend.example.com/mcp"
        assert args.oidc_issuer_url == "https://env-auth.example.com"
        assert args.oidc_client_id == "env-client"
        assert args.oidc_client_secret == "env-secret"
        assert args.oidc_scopes == "openid email"
        assert args.oidc_redirect_url == "http://localhost:9090/callback"

    def test_cli_args_override_env_vars(self):
        """Test that CLI arguments take precedence over environment variables."""
        env_vars = {
            "MCP_BACKEND_URL": "http://env-backend.example.com/mcp",
            "OIDC_ISSUER_URL": "https://env-auth.example.com",
        }

        test_args = [
            "http://cli-backend.example.com/mcp",
            "--oidc-issuer-url",
            "https://cli-auth.example.com",
        ]

        with patch("sys.argv", ["authful-mcp-proxy"] + test_args):
            with patch.dict(os.environ, env_vars):
                args = cli()

        assert args.mcp_backend_url == "http://cli-backend.example.com/mcp"
        assert args.oidc_issuer_url == "https://cli-auth.example.com"

    def test_cli_debug_flag(self):
        """Test debug flag sets debug to True."""
        test_args = ["http://backend.example.com/mcp", "--debug"]

        with patch("sys.argv", ["authful-mcp-proxy"] + test_args):
            args = cli()

        assert args.debug is True
        assert args.silent is False

    def test_cli_silent_flag(self):
        """Test silent flag sets silent to True."""
        test_args = ["http://backend.example.com/mcp", "--silent"]

        with patch("sys.argv", ["authful-mcp-proxy"] + test_args):
            args = cli()

        assert args.silent is True
        assert args.debug is False

    def test_cli_debug_env_var(self):
        """Test MCP_PROXY_DEBUG environment variable."""
        test_args = ["http://backend.example.com/mcp"]

        with patch("sys.argv", ["authful-mcp-proxy"] + test_args):
            with patch.dict(os.environ, {"MCP_PROXY_DEBUG": "true"}):
                args = cli()

        assert args.debug is True

    def test_cli_no_banner_flag(self):
        """Test --no-banner flag."""
        test_args = ["http://backend.example.com/mcp", "--no-banner"]

        with patch("sys.argv", ["authful-mcp-proxy"] + test_args):
            args = cli()

        assert args.no_banner is True

    def test_cli_transport_default_is_stdio(self):
        """Test that transport defaults to stdio when not specified."""
        with patch("sys.argv", ["authful-mcp-proxy", "http://backend.example.com/mcp"]):
            args = cli()

        assert args.transport == "stdio"

    def test_cli_transport_stdio_explicit(self):
        """Test explicit --transport stdio."""
        test_args = ["http://backend.example.com/mcp", "--transport", "stdio"]

        with patch("sys.argv", ["authful-mcp-proxy"] + test_args):
            args = cli()

        assert args.transport == "stdio"

    def test_cli_transport_http(self):
        """Test --transport http."""
        test_args = ["http://backend.example.com/mcp", "--transport", "http"]

        with patch("sys.argv", ["authful-mcp-proxy"] + test_args):
            args = cli()

        assert args.transport == "http"

    def test_cli_transport_env_var(self):
        """Test MCP_TRANSPORT environment variable fallback."""
        with patch("sys.argv", ["authful-mcp-proxy", "http://backend.example.com/mcp"]):
            with patch.dict(os.environ, {"MCP_TRANSPORT": "http"}):
                args = cli()

        assert args.transport == "http"

    def test_cli_transport_cli_overrides_env_var(self):
        """Test that --transport takes precedence over MCP_TRANSPORT env var."""
        test_args = ["http://backend.example.com/mcp", "--transport", "stdio"]

        with patch("sys.argv", ["authful-mcp-proxy"] + test_args):
            with patch.dict(os.environ, {"MCP_TRANSPORT": "http"}):
                args = cli()

        assert args.transport == "stdio"

    def test_cli_host_arg(self):
        """Test --host argument."""
        test_args = [
            "http://backend.example.com/mcp",
            "--transport",
            "http",
            "--host",
            "127.0.0.1",
        ]

        with patch("sys.argv", ["authful-mcp-proxy"] + test_args):
            args = cli()

        assert args.host == "127.0.0.1"

    def test_cli_port_arg(self):
        """Test --port argument is parsed as integer."""
        test_args = [
            "http://backend.example.com/mcp",
            "--transport",
            "http",
            "--port",
            "9000",
        ]

        with patch("sys.argv", ["authful-mcp-proxy"] + test_args):
            args = cli()

        assert args.port == 9000

    def test_cli_host_env_var(self):
        """Test MCP_HOST environment variable fallback."""
        with patch("sys.argv", ["authful-mcp-proxy", "http://backend.example.com/mcp"]):
            with patch.dict(os.environ, {"MCP_HOST": "192.168.1.1"}):
                args = cli()

        assert args.host == "192.168.1.1"

    def test_cli_port_env_var(self):
        """Test MCP_PORT environment variable fallback is converted to int."""
        with patch("sys.argv", ["authful-mcp-proxy", "http://backend.example.com/mcp"]):
            with patch.dict(os.environ, {"MCP_PORT": "9000"}):
                args = cli()

        assert args.port == 9000

    def test_cli_host_port_none_by_default(self):
        """Test that host and port are None when not provided (FastMCP uses its own defaults)."""
        with patch("sys.argv", ["authful-mcp-proxy", "http://backend.example.com/mcp"]):
            with patch.dict(os.environ, {}, clear=True):
                args = cli()

        assert args.host is None
        assert args.port is None


class TestGetLogLevelName:
    """Test get_log_level_name function."""

    def test_silent_mode(self):
        """Test that silent mode returns ERROR level."""

        class Args:
            silent = True
            debug = False

        level = get_log_level_name(Args())
        assert level == logging.getLevelName(logging.ERROR)

    def test_debug_mode(self):
        """Test that debug mode returns DEBUG level."""

        class Args:
            silent = False
            debug = True

        level = get_log_level_name(Args())
        assert level == logging.getLevelName(logging.DEBUG)

    def test_normal_mode(self):
        """Test that normal mode returns INFO level."""

        class Args:
            silent = False
            debug = False

        level = get_log_level_name(Args())
        assert level == logging.getLevelName(logging.INFO)
