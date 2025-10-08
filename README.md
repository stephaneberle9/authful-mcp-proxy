<!-- omit from toc -->
Authful MCP Proxy
=================

A [Model Context Protocol](https://modelcontextprotocol.com) (MCP) proxy server that performs OIDC authentication to obtain access tokens for remote MCP servers protected by token validation, and bridges HTTP transport to local stdio for MCP clients like Claude Desktop.

- [Description](#description)
- [Development](#development)
  - [Setup](#setup)
  - [Run](#run)
    - [Inside dev environment](#inside-dev-environment)
    - [Outside dev environment](#outside-dev-environment)
    - [With MCP Inspector](#with-mcp-inspector)
    - [With minimal token-validating MCP backend example](#with-minimal-token-validating-mcp-backend-example)
  - [Check](#check)
    - [Enable automatic execution on git commit](#enable-automatic-execution-on-git-commit)
    - [Manual execution](#manual-execution)
  - [Test](#test)
    - [Quick start](#quick-start)
  - [Package](#package)
- [Usage](#usage)
  - [Connect MCP client](#connect-mcp-client)
    - [Claude Desktop](#claude-desktop)
      - [Option 1: With MCP proxy server from PyPI](#option-1-with-mcp-proxy-server-from-pypi)
      - [Option 2: With MCP proxy server from the sources](#option-2-with-mcp-proxy-server-from-the-sources)

# Description

Typically, securing MCP connections with OAuth or OpenID connect (OIDC) requires "authful" MCP servers that [coordinate with external identity providers](https://gofastmcp.com/servers/auth/authentication#external-identity-providers). MCP clients handle authentication through the MCP server, which in turn interacts with the OAuth or OIDC authorization server. However, this doesn't work with MCP servers only protected by [token validation](https://gofastmcp.com/servers/auth/authentication#token-validation), i.e., MCP servers that trust tokens from a known issuer but don't coordinate with the OAuth/OIDC authorization server themselves. In such scenarios, MCP clients detect the MCP server isn't authful and skip the OAuth/OIDC authentication entirely, resulting in `401 Unauthorized` errors for all tool, resource, and prompt requests.

This MCP proxy fills that gap by handling authentication independently through direct OIDC authorization server interaction. It performs the OAuth authorization code flow by opening the user's browser to the OIDC authorization endpoint for login and scope approval. A temporary local HTTP server receives the OAuth redirect and exchanges the authorization code for access and refresh tokens using PKCE. The access token is used as a Bearer token for all backend MCP server requests and cached locally to avoid repeated browser interactions. When tokens expire, the proxy automatically obtains new ones using the refresh token.

# Development

## Setup

- Install [Python 3.12](https://www.python.org/downloads) or later
- Install required development tools:

  ```bash
  # Install build tools and uv package manager
  python -m pip install build uv
  ```

## Run

### Inside dev environment

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

### Outside dev environment

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
          "OIDC_CLIENT_ID": "xxxxxxxx",
          "OIDC_CLIENT_SECRET": "xxxxxxxx", // optional for public OIDC clients not requiring any such
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

### With minimal token-validating MCP backend example

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

### Enable automatic execution on git commit

```bash
# Activate virtual environment
.venv\Scripts\activate  # Windows
source ./.venv/bin/activate  # Linux/macOS

# Install pre-commit hooks
uv run pre-commit install
```

### Manual execution

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

- **Unit tests**: Test individual components (schema provider, query translator) in isolation
- **Integration tests**: Test MCP tools and resources with realistic data flows
- **Coverage requirement**: Minimum 85% code coverage

### Quick start

```bash
# Activate virtual environment
.venv\Scripts\activate  # Windows
source ./.venv/bin/activate  # Linux/macOS

# Run all tests
uv run pytest

# Run tests with coverage report
uv run pytest --cov=src/authful_mcp_proxy --cov-report=html
```

For detailed information wrt testing, see [tests/README.md](tests/README.md).

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

# Usage

## Connect MCP client

### Claude Desktop

#### Option 1: With MCP proxy server from PyPI

- Open _Claude Desktop_ configuration JSON file (accessible from _Claude Desktop_ > `Settings...` > `Developer` > `Edit config`
- Add the following entry under `mcpServers`:

  ```jsonc
  {
    "mcpServers": {
      "proxied-mcp-server": {
        "command": "uvx",
        "args": [
          "authful-mcp-proxy",
          "https://mcp-backend.company.com/mcp"
        ],
        "env": {
          "OIDC_ISSUER_URL": "https://auth.company.com",
          "OIDC_CLIENT_ID": "xxxxxxxx",
          "OIDC_CLIENT_SECRET": "xxxxxxxx", // optional for public OIDC clients not requiring any such
          "OIDC_SCOPES": "openid profile",
          "OIDC_REDIRECT_URL": "http://localhost:8080/auth/callback"
        }
      }
    }
  }
  ```

- Close _Claude Desktop_ and restart it to apply the changes

#### Option 2: With MCP proxy server from the sources

- Open _Claude Desktop_ configuration JSON file (accessible from _Claude Desktop_ > `Settings...` > `Developer` > `Edit config`
- Add the following entry under `mcpServers`:

  ```jsonc
  {
    "mcpServers": {
      "proxied-mcp-server": {
        "command": "uv",
        "args": [
          "run",
          "--with-editable",
          "/absolute path/to/authful-mcp-proxy project",
          "authful-mcp-proxy",
          "https://mcp-backend.company.com/mcp"
        ],
        "env": {
          "OIDC_ISSUER_URL": "https://auth.company.com",
          "OIDC_CLIENT_ID": "xxxxxxxx",
          "OIDC_CLIENT_SECRET": "xxxxxxxx", // optional for public OIDC clients not requiring any such
          "OIDC_SCOPES": "openid profile",
          "OIDC_REDIRECT_URL": "http://localhost:8080/auth/callback"
        }
      }
    }
  }
  ```

- Close _Claude Desktop_ and restart it to apply the changes
