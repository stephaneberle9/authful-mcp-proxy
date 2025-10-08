<!-- omit from toc -->
Authful MCP Proxy
=================

A [Model Context Protocol](https://modelcontextprotocol.com) (MCP) proxy server that performs OIDC authentication to obtain access tokens for remote MCP servers protected by token validation, and bridges HTTP transport to local stdio for MCP clients like Claude Desktop.

- [What Is This For?](#what-is-this-for)
  - [Technical Background](#technical-background)
- [Usage](#usage)
  - [Quick Start](#quick-start)
    - [First Run](#first-run)
  - [Configuration Options](#configuration-options)
    - [Required Configuration](#required-configuration)
    - [Optional Configuration](#optional-configuration)
    - [Advanced Options](#advanced-options)
  - [Usage Examples](#usage-examples)
    - [Example 1: Claude Desktop (Recommended)](#example-1-claude-desktop-recommended)
    - [Example 2: Using Latest Version](#example-2-using-latest-version)
    - [Example 3: With Client Secret (Confidential Client)](#example-3-with-client-secret-confidential-client)
    - [Example 4: Custom Redirect Port](#example-4-custom-redirect-port)
    - [Example 5: Development from Source](#example-5-development-from-source)
    - [Example 6: Debug Mode](#example-6-debug-mode)
  - [Using with Other MCP Clients](#using-with-other-mcp-clients)
    - [MCP Inspector](#mcp-inspector)
    - [Cursor / Windsurf](#cursor--windsurf)
    - [Command Line / Direct Usage](#command-line--direct-usage)
  - [Credential Management](#credential-management)
    - [Where Are Credentials Stored?](#where-are-credentials-stored)
    - [Clear Cached Credentials](#clear-cached-credentials)
  - [Troubleshooting](#troubleshooting)
    - [Browser Doesn't Open for Authentication](#browser-doesnt-open-for-authentication)
    - [401 Unauthorized Errors](#401-unauthorized-errors)
    - [Redirect URI Mismatch](#redirect-uri-mismatch)
    - [Token Refresh Failures](#token-refresh-failures)
    - [Connection to Backend Fails](#connection-to-backend-fails)
    - [MCP Client Doesn't Recognize the Proxy](#mcp-client-doesnt-recognize-the-proxy)
    - [Debug Logging](#debug-logging)
    - [Still Having Issues?](#still-having-issues)
- [Development](#development)
  - [Setup](#setup)
  - [Run](#run)
    - [Inside Dev Environment](#inside-dev-environment)
    - [Outside Dev Environment](#outside-dev-environment)
    - [With MCP Inspector](#with-mcp-inspector)
    - [With Minimal Token-Validating MCP Backend Example](#with-minimal-token-validating-mcp-backend-example)
  - [Check](#check)
    - [Enable Automatic Execution on Git Commit](#enable-automatic-execution-on-git-commit)
    - [Manual Execution](#manual-execution)
  - [Test](#test)
  - [Package](#package)

# What Is This For?

Use `authful-mcp-proxy` when you need to connect your MCP client (like Claude Desktop, Cursor, or Windsurf) to a remote MCP server that:
- Is protected by OAuth/OIDC token validation
- Doesn't handle authentication itself (no built-in OAuth flows)
- Returns `401 Unauthorized` without proper access tokens

The proxy handles the full OIDC authentication flow, securely stores your credentials in `~/.fastmcp/oauth-mcp-client-cache/`, and automatically refreshes tokens as needed.

## Technical Background

Typically, securing MCP connections with OAuth or OpenID connect (OIDC) requires "authful" MCP servers that [coordinate with external identity providers](https://gofastmcp.com/servers/auth/authentication#external-identity-providers). MCP clients handle authentication through the MCP server, which in turn interacts with the OAuth or OIDC authorization server. However, this doesn't work with MCP servers only protected by [token validation](https://gofastmcp.com/servers/auth/authentication#token-validation), i.e., MCP servers that trust tokens from a known issuer but don't coordinate with the OAuth/OIDC authorization server themselves. In such scenarios, MCP clients detect the MCP server isn't authful and skip the OAuth/OIDC authentication entirely, resulting in `401 Unauthorized` errors for all tool, resource, and prompt requests.

This MCP proxy fills that gap by handling authentication independently through direct OIDC authorization server interaction. It performs the OAuth authorization code flow by opening the user's browser to the OIDC authorization endpoint for login and scope approval. A temporary local HTTP server receives the OAuth redirect and exchanges the authorization code for access and refresh tokens using PKCE. The access token is used as a Bearer token for all backend MCP server requests and cached locally to avoid repeated browser interactions. When tokens expire, the proxy automatically obtains new ones using the refresh token.

# Usage

## Quick Start

The simplest way to use `authful-mcp-proxy` with MCP clients like Claude Desktop:

```jsonc
{
  "mcpServers": {
    "my-protected-server": {
      "command": "uvx",
      "args": [
        "authful-mcp-proxy",
        "https://mcp-backend.company.com/mcp"
      ],
      "env": {
        "OIDC_ISSUER_URL": "https://auth.company.com",
        "OIDC_CLIENT_ID": "your-client-id"
      }
    }
  }
}
```

> ℹ️ **Note:** Only two really essential OIDC parameters (issuer URL and client ID) must be specified. Other OIDC parameters (scopes, redirect URL, etc.) use defaults that can be found in the [Configuration Options](#configuration-options) section below.

> ⚠️ **Important:** Make sure your OIDC client is configured with `http://localhost:8080/auth/callback` as an allowed redirect URI!

### First Run

The proxy will open your browser for authentication. After you log in and approve the required scopes, your credentials are cached locally and you won't need to authenticate again until tokens expire.

## Configuration Options

All options can be set via environment variables in the `env` block or passed as CLI arguments (see `uvx authful-mcp-proxy --help`).

### Required Configuration

| Environment Variable | Description | Example |
|---------------------|-------------|---------|
| `MCP_BACKEND_URL` | Remote MCP server URL (can also be first argument) | `https://mcp.example.com/mcp` |
| `OIDC_ISSUER_URL` | Your OIDC provider's issuer URL | `https://auth.example.com` |
| `OIDC_CLIENT_ID` | OAuth client ID from your OIDC provider | `my-app-client-id` |

### Optional Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `OIDC_CLIENT_SECRET` | _(none)_ | Client secret (not needed for public clients that don't require any such) |
| `OIDC_SCOPES` | `openid profile email` | Space-separated OAuth scopes |
| `OIDC_REDIRECT_URL` | `http://localhost:8080/auth/callback` | OAuth callback URL |

### Advanced Options

| CLI Flag | Description |
|----------|-------------|
| `--no-banner` | Suppress the startup banner |
| `--silent` | Show only error messages |
| `--debug` | Enable detailed debug logging |

## Usage Examples

### Example 1: Claude Desktop (Recommended)

Add to your Claude Desktop config (accessible via Settings → Developer → Edit Config):

```jsonc
{
  "mcpServers": {
    "company-tools": {
      "command": "uvx",
      "args": [
        "authful-mcp-proxy",
        "https://mcp-backend.company.com/mcp"
      ],
      "env": {
        "OIDC_ISSUER_URL": "https://auth.company.com",
        "OIDC_CLIENT_ID": "claude-desktop-client",
        "OIDC_SCOPES": "openid profile mcp:read mcp:write"
      }
    }
  }
}
```

> ⚠️ **Important:** Make sure your OIDC client is configured with `http://localhost:8080/auth/callback` as an allowed redirect URI!

Restart Claude Desktop to apply changes.

### Example 2: Using Latest Version

To always use the latest version from PyPI (auto-updates):

```jsonc
{
  "mcpServers": {
    "my-server": {
      "command": "uvx",
      "args": [
        "authful-mcp-proxy@latest",
        "https://mcp.example.com/mcp"
      ],
      "env": {
        "OIDC_ISSUER_URL": "https://auth.example.com",
        "OIDC_CLIENT_ID": "my-client-id"
      }
    }
  }
}
```

> ⚠️ **Important:** Make sure your OIDC client is configured with `http://localhost:8080/auth/callback` as an allowed redirect URI!

### Example 3: With Client Secret (Confidential Client)

For OIDC confidential clients requiring a secret:

```jsonc
{
  "mcpServers": {
    "secure-server": {
      "command": "uvx",
      "args": ["authful-mcp-proxy", "https://api.example.com/mcp"],
      "env": {
        "OIDC_ISSUER_URL": "https://login.example.com",
        "OIDC_CLIENT_ID": "your-confidential-client-id",
        "OIDC_CLIENT_SECRET": "your-client-secret",
        "OIDC_SCOPES": "openid profile email api:access"
      }
    }
  }
}
```

> ⚠️ **Important:** Make sure your OIDC client is configured with `http://localhost:8080/auth/callback` as an allowed redirect URI!

### Example 4: Custom Redirect Port

If port 8080 is already in use, specify a different port:

```jsonc
{
  "mcpServers": {
    "my-server": {
      "command": "uvx",
      "args": ["authful-mcp-proxy", "https://mcp.example.com"],
      "env": {
        "OIDC_ISSUER_URL": "https://auth.example.com",
        "OIDC_CLIENT_ID": "my-client-id",
        "OIDC_REDIRECT_URL": "http://localhost:9090/auth/callback"
      }
    }
  }
}
```

> ⚠️ **Important:** Make sure your OIDC client is configured with the chosen redirect URL as an allowed redirect URI!

### Example 5: Development from Source

When developing or testing local changes:

```jsonc
{
  "mcpServers": {
    "local-dev": {
      "command": "uv",
      "args": [
        "run",
        "--with-editable",
        "/path/to/authful-mcp-proxy",
        "authful-mcp-proxy",
        "https://mcp.example.com/mcp"
      ],
      "env": {
        "OIDC_ISSUER_URL": "https://auth.example.com",
        "OIDC_CLIENT_ID": "dev-client"
      }
    }
  }
}
```

> ⚠️ **Important:** Make sure your OIDC client is configured with `http://localhost:8080/auth/callback` as an allowed redirect URI!

### Example 6: Debug Mode

Enable detailed logging for troubleshooting:

```jsonc
{
  "mcpServers": {
    "debug-server": {
      "command": "uvx",
      "args": [
        "authful-mcp-proxy",
        "--debug",
        "https://mcp.example.com"
      ],
      "env": {
        "OIDC_ISSUER_URL": "https://auth.example.com",
        "OIDC_CLIENT_ID": "my-client-id"
      }
    }
  }
}
```

> ⚠️ **Important:** Make sure your OIDC client is configured with `http://localhost:8080/auth/callback` as an allowed redirect URI!

## Using with Other MCP Clients

### MCP Inspector

Create an `mcp.json` file:

```jsonc
{
  "mcpServers": {
    "authful-proxy": {
      "command": "uvx",
      "args": ["authful-mcp-proxy", "https://mcp.example.com/mcp"],
      "env": {
        "OIDC_ISSUER_URL": "https://auth.example.com",
        "OIDC_CLIENT_ID": "inspector-client"
      }
    }
  }
}
```

> ⚠️ **Important:** Make sure your OIDC client is configured with `http://localhost:8080/auth/callback` as an allowed redirect URI!

Start the inspector:
```bash
npx @modelcontextprotocol/inspector --config mcp.json --server authful-proxy
```

### Cursor / Windsurf

These editors use the same configuration format as Claude Desktop. Add the server config to your MCP settings file.

### Command Line / Direct Usage

```bash
# Install globally
uvx authful-mcp-proxy --help

# Run directly
uvx authful-mcp-proxy \
  --oidc-issuer-url https://auth.example.com \
  --oidc-client-id my-client \
  https://mcp.example.com/mcp
```

## Credential Management

### Where Are Credentials Stored?

Credentials are cached in `~/.fastmcp/oauth-mcp-client-cache/` with filenames based on the OIDC issuer URL:
```
~/.fastmcp/oauth-mcp-client-cache/
  └── https_auth_example_com_tokens.json
```

### Clear Cached Credentials

To force re-authentication (e.g., to switch accounts or clear expired tokens):

```bash
# Linux/macOS
rm -rf ~/.fastmcp/oauth-mcp-client-cache/

# Windows
rmdir /s %USERPROFILE%\.fastmcp\oauth-mcp-client-cache
```

The next time you connect, you'll be prompted to authenticate again.

## Troubleshooting

### Browser Doesn't Open for Authentication

**Problem:** The proxy starts but no browser window opens.

**Solutions:**
1. Check that port 8080 (or your custom redirect port) isn't blocked
2. Manually open the URL shown in the proxy logs
3. Verify your firewall isn't blocking localhost connections

### 401 Unauthorized Errors

**Problem:** Backend MCP server returns 401 errors.

**Solutions:**
1. Verify `OIDC_ISSUER_URL` matches your provider exactly
2. Check that `OIDC_CLIENT_ID` is correct
3. Ensure requested scopes are granted by the authorization server
4. Clear cached credentials and re-authenticate: `rm -rf ~/.fastmcp/oauth-mcp-client-cache/`
5. Enable debug mode to see token details: `--debug`

### Redirect URI Mismatch

**Problem:** OIDC provider shows "redirect_uri mismatch" error.

**Solutions:**
1. Add `http://localhost:8080/auth/callback` to your OIDC client's allowed redirect URIs
2. If using a custom port, update both the proxy config (`OIDC_REDIRECT_URL`) and OIDC client settings
3. Ensure the redirect URI matches exactly (including trailing slashes)

### Token Refresh Failures

**Problem:** Proxy works initially but fails after some time.

**Solutions:**
1. Check if your OIDC provider issued a refresh token (some providers don't for certain grant types)
2. Verify the `offline_access` scope is requested if required by your provider
3. Clear cached credentials to get new tokens: `rm -rf ~/.fastmcp/oauth-mcp-client-cache/`

### Connection to Backend Fails

**Problem:** Can't connect to remote MCP server.

**Solutions:**
1. Verify the backend URL is correct and accessible
2. Check network connectivity to the backend server
3. Ensure the backend server is running and accepting connections
4. Try accessing the backend URL directly in a browser to verify it's reachable
5. Check for proxy/VPN issues that might block the connection

### MCP Client Doesn't Recognize the Proxy

**Problem:** Claude Desktop or other client shows error about the server.

**Solutions:**
1. Verify JSON syntax is correct (no trailing commas, proper quotes)
2. Check that `uvx` or `uv` is in your PATH
3. Restart your MCP client completely (not just refresh)
4. Review client logs for specific error messages

### Debug Logging

Enable debug mode to see detailed information about the authentication flow:

```bash
uvx authful-mcp-proxy --debug https://mcp.example.com/mcp
```

Or via environment variable:
```jsonc
{
  "env": {
    "MCP_PROXY_DEBUG": "1",
    // ... other config
  }
}
```

### Still Having Issues?

1. Check the [examples directory](examples/token_validating_mcp_backend/) for a working test setup
2. Run with `--debug` to get detailed logs
3. Verify your OIDC provider configuration
4. Open an issue on GitHub with debug logs (redact sensitive information)

# Development

## Setup

- Install [Python 3.12](https://www.python.org/downloads) or later
- Install required development tools:

  ```bash
  # Install build tools and uv package manager
  python -m pip install build uv
  ```

## Run

### Inside Dev Environment

```bash
# Create virtual environment
uv venv

# Activate virtual environment
.venv\Scripts\activate  # Windows
source ./.venv/bin/activate  # Linux/macOS

# Install project in editable mode with live code reloading
uv sync

# Run the MCP server:

# (see --help for CLI options)
authful-mcp-proxy [options] https://mcp-backend.company.com/mcp
# or
uv run --env-file .env authful-mcp-proxy [options]

# Stop the server
# Press Ctrl+C to exit

# Deactivate virtual environment when done
deactivate
```

### Outside Dev Environment

```bash
# Run the MCP server directly from the sources (see --help for CLI options)
uv run --env-file .env --project "/absolute path/to/authful-mcp-proxy project" authful-mcp-proxy [options]

# Run as editable install to enable live code reloading during development (see --help for CLI options)
uv run --env-file .env --with-editable "/absolute path/to/authful-mcp-proxy project" authful-mcp-proxy [options]
```

### With MCP Inspector

Create an `mcp.json` file containing:

```jsonc
{
  "mcpServers": {
    "authful-mcp-proxy": {
      "command": "uv",
      "args": [
        "run",
        "--env-file", // optional, can also be provided via "env" object
        ".env",
        "authful-mcp-proxy",
        "https://mcp-backend.company.com/mcp"
      ],
      // Optional, can also be provided via .env file
      "env": {
          "OIDC_ISSUER_URL": "https://auth.company.com",
          "OIDC_CLIENT_ID": "your-client-id",
          "OIDC_CLIENT_SECRET": "your-client-secret", // optional for public OIDC clients that don't require any such
          "OIDC_SCOPES": "openid profile",
          "OIDC_REDIRECT_URL": "http://localhost:8080/auth/callback"
      }
    }
  }
}
```

From a terminal, start the MCP Inspector:

```bash
# Start and open MCP Inspector in your browser
npx -y @modelcontextprotocol/inspector --config mcp.json --server authful-mcp-proxy
```

In your browser, connect to your MCP proxy server, authenticate and use the tools, resources and prompts of the backend MCP server:
- Connect to MCP proxy server: `Connect`
- Sign up/sign in and approve required scopes as needed
- List tools of backend MCP server: `Tools` > `List Tools`
- Find MCP proxy server logs under `Server Notifications`

### With Minimal Token-Validating MCP Backend Example

For quick testing without a real remote MCP server, run the minimal token-validating MCP backend example:

```bash
# Change to example MCP backend directory
cd examples/token_validating_mcp_backend

# Create virtual environment
uv venv

# Activate virtual environment
.venv\Scripts\activate  # Windows
source ./.venv/bin/activate  # Linux/macOS

# Install required dependencies
uv pip install -r requirements.txt

# Run the minimal example MCP client
uv run --env-file .env mcp_backend.py
```

## Check

This project uses `pre-commit` hooks for running static checks to maintain high code quality standards. These static checks include:

- **Ruff**: Python linting and code formatting
- **ty**: Modern type checking for Python
- **Prettier**: JSON, YAML, and Markdown formatting
- **Codespell**: Common spelling error detection
- **pyproject.toml validation**: Project configuration validation

### Enable Automatic Execution on Git Commit

```bash
# Activate virtual environment
.venv\Scripts\activate  # Windows
source ./.venv/bin/activate  # Linux/macOS

# Install pre-commit hooks
uv run pre-commit install
```

### Manual Execution

```bash
# Run all checks on all files
uv run pre-commit run --all-files

# Run individual tools
uv run ruff format          # Code formatting
uv run ruff check --fix     # Linting with auto-fix
uv run ty check             # Type checking
```

## Test

This project includes a comprehensive test suite to ensure reliability and maintainability of the MCP proxy server functionality. They include:

- **Unit tests**: Test configuration, OIDC authentication, and main application components
- **Integration tests**: Test end-to-end OIDC flows with realistic scenarios
- **Coverage tracking**: Code coverage reports generated automatically (see `htmlcov/` directory)

```bash
# Activate virtual environment
.venv\Scripts\activate  # Windows
source ./.venv/bin/activate  # Linux/macOS

# Install project dependencies (includes both dev and test groups)
uv sync

# Run all tests
uv run pytest

# Run with verbose output
uv run pytest -v

# Run with coverage report output to terminal and enforce minimum coverage
uv run pytest --cov=src/authful_mcp_proxy --cov-report=term-missing --cov-fail-under=65

# Run specific test file
uv run pytest tests/test_main.py

# Run specific test class
uv run pytest tests/test_main.py::TestCLI

# Run specific test
uv run pytest tests/test_main.py::TestCLI::test_cli_with_minimal_args

# Generate HTML coverage report
uv run pytest --cov-report=html
# Open htmlcov/index.html to view detailed coverage
```

## Package

For publishing to PyPI or integrating with Python package managers:

```bash
# Activate virtual environment
.venv\Scripts\activate  # Windows
source ./.venv/bin/activate  # Linux/macOS

# Install project dependencies
uv sync --no-dev

# Build distribution packages
uv build
```

This will create a `dist` folder containing an `authful_mcp_proxy X.X.X.tar.gz` and an `authful_mcp_proxy X.X.X-py3-none-any.whl` file.

