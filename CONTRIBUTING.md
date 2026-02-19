# Contributing to Authful MCP Proxy

Thank you for your interest in contributing! This document covers development setup, testing, and the release process.

## Table of Contents

- [Contributing to Authful MCP Proxy](#contributing-to-authful-mcp-proxy)
  - [Table of Contents](#table-of-contents)
  - [Development Setup](#development-setup)
  - [Running the Project](#running-the-project)
    - [Inside Dev Environment](#inside-dev-environment)
    - [Outside Dev Environment](#outside-dev-environment)
    - [With MCP Inspector](#with-mcp-inspector)
    - [With Claude Desktop](#with-claude-desktop)
    - [With Minimal Token-Validating MCP Backend Example](#with-minimal-token-validating-mcp-backend-example)
  - [Code Quality](#code-quality)
    - [Pre-commit Hooks](#pre-commit-hooks)
    - [Manual Checks](#manual-checks)
  - [Testing](#testing)
  - [CI/CD Workflows](#cicd-workflows)
    - [Static Analysis](#static-analysis)
    - [Test Suite](#test-suite)
    - [Publishing](#publishing)
  - [Creating a Release](#creating-a-release)
  - [Building Packages](#building-packages)
  - [Dependency Management and Lock Files](#dependency-management-and-lock-files)
    - [Why `uvx` Doesn't Use `uv.lock`](#why-uvx-doesnt-use-uvlock)
    - [Ensuring Compatibility for `uvx` Users](#ensuring-compatibility-for-uvx-users)
    - [When to Update `uv.lock`](#when-to-update-uvlock)

## Development Setup

- Install [Python 3.10](https://www.python.org/downloads) or later
- Install required development tools:

  ```bash
  # Install build tools and uv package manager
  python -m pip install build uv
  ```

## Running the Project

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
uv run --env-file /path/to/authful-mcp-proxy/.env --project "/path/to/authful-mcp-proxy" authful-mcp-proxy [options]

# Run as editable install to enable live code reloading during development (see --help for CLI options)
uv run --env-file /path/to/authful-mcp-proxy/.env --with-editable "/path/to/authful-mcp-proxy" authful-mcp-proxy [options]
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
          "OIDC_CLIENT_SECRET": "your-client-secret", // to be omitted for public OIDC clients that don't require any such
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

### With Claude Desktop

Add the following to your Claude Desktop configuration file (`claude_desktop_config.json`), adjusting the paths to match your local setup:

- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

```jsonc
{
  "mcpServers": {
    "authful-mcp-proxy": {
      "command": "uv",
      "args": [
        "run",
        "--env-file", // optional, can also be provided via "env" object
        "/path/to/authful-mcp-proxy/.env",
        "--with-editable",
        "/path/to/authful-mcp-proxy",
        "authful-mcp-proxy",
        "https://mcp-backend.company.com/mcp"
      ],
      // Optional, can also be provided via .env file
      "env": {
        "OIDC_ISSUER_URL": "https://auth.company.com",
        "OIDC_CLIENT_ID": "your-client-id",
        "OIDC_CLIENT_SECRET": "your-client-secret", // to be omitted for public OIDC clients that don't require any such
        "OIDC_SCOPES": "openid profile",
        "OIDC_REDIRECT_URL": "http://localhost:8080/auth/callback"
      }
    }
  }
}
```

After saving the configuration, restart Claude Desktop. Then:

- Sign up/sign in and approve required scopes as needed
- Open a new chat, click `+` and verify that `authful-mcp-proxy` appears under `Connectors`
- Use the tools, resources and prompts of the backend MCP server

If an error popup appears, open the MCP server logs to diagnose the issue:

- **Windows**: `%LOCALAPPDATA%\Claude\Logs\mcp-server-authful-mcp-proxy.log`
- **macOS**: `~/Library/Logs/Claude/mcp-server-authful-mcp-proxy.log`

Alternatively, go to `Settings` > `Developer` > select `authful-mcp-proxy` > `Open Logs Folder`.

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

## Code Quality

This project uses `pre-commit` hooks for running static checks to maintain high code quality standards. These static checks include:

- **Ruff**: Python linting and code formatting
- **ty**: Modern type checking for Python
- **Prettier**: JSON, YAML, and Markdown formatting
- **Codespell**: Common spelling error detection
- **pyproject.toml validation**: Project configuration validation

### Pre-commit Hooks

```bash
# Activate virtual environment
.venv\Scripts\activate  # Windows
source ./.venv/bin/activate  # Linux/macOS

# Install pre-commit hooks
uv run pre-commit install
```

### Manual Checks

```bash
# Run all checks on all files
uv run pre-commit run --all-files

# Run individual tools
uv run ruff format          # Code formatting
uv run ruff check --fix     # Linting with auto-fix
uv run ty check             # Type checking
```

## Testing

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

## CI/CD Workflows

This project uses GitHub Actions for continuous integration and deployment. All workflows are located in `.github/workflows/`.

### Static Analysis

**Workflow:** `run-static.yml`

Runs automatically on:
- Push to `main` branch (when source files change)
- All pull requests
- Manual trigger via workflow dispatch

Checks performed:
- Verifies `uv.lock` is up to date
- Runs all pre-commit hooks (Ruff, ty, Prettier, Codespell, etc.)

### Test Suite

**Workflow:** `run-tests.yml`

Runs automatically on:
- Push to `main` branch (when source files change)
- All pull requests
- Manual trigger via workflow dispatch

Test matrix:
- **OS**: Ubuntu, Windows
- **Python**: 3.10

### Publishing

**Workflow:** `publish.yml` (PyPI)

Runs automatically when a GitHub Release is published. Can also be triggered manually.

**Workflow:** `publish-test.yml` (TestPyPI)

Manual trigger only. Use this to test the publishing process before creating a real release.

Both workflows:
- Build the package using `uv build`
- Validate the version format (rejects development versions like `0.1.0.dev1`)
- Publish using PyPI trusted publishing (no API tokens needed)

## Creating a Release

To create a new release and publish to PyPI:

1. **Ensure all tests pass** on the `main` branch

2. **Create and push a version tag:**
   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```

3. **Create a GitHub Release:**
   - Go to [Releases](../../releases) on GitHub
   - Click "Draft a new release"
   - Select the tag you just created
   - Add release notes describing the changes
   - Click "Publish release"

4. **Automatic publishing:** The `publish.yml` workflow will automatically:
   - Build the package
   - Validate the version
   - Publish to PyPI

**Version format:** The version is derived from the Git tag using `uv-dynamic-versioning`. Tags must follow the format `vX.Y.Z` (e.g., `v0.1.0`, `v1.2.3`).

**Testing the release process:** Use the "Publish to TestPyPI" workflow to verify everything works before creating a real release.

## Building Packages

For local package building or manual publishing:

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

## Dependency Management and Lock Files

### Why `uvx` Doesn't Use `uv.lock`

When users run `uvx authful-mcp-proxy`, the `uv.lock` file is **not used**. This is by design and is standard Python packaging practice:

1. **Wheels don't contain lock files**: When publishing to PyPI, the wheel format (preferred by installers) only contains:
   - Package code
   - Metadata from `pyproject.toml`
   - Licenses
   
   The `uv.lock` file is deliberately excluded from wheels.

2. **Lock files are development tools**: The `uv.lock` file ensures reproducible development environments when using `uv sync`. It's not part of the PEP 517/621 distribution metadata standard.

3. **uvx creates ephemeral environments**: When running `uvx authful-mcp-proxy`:
   - Downloads the package from PyPI (usually the wheel)
   - Creates a temporary virtual environment
   - Resolves dependencies from package metadata (derived from `pyproject.toml`)
   - No mechanism exists to read or use lock files from the installed package

### Ensuring Compatibility for `uvx` Users

To ensure users get compatible dependency versions when running `uvx authful-mcp-proxy`, we use **version constraints in `pyproject.toml`**:

```toml
dependencies = [
    "fastmcp>=2.14.0,<3.0.0",  # Prevents incompatible fastmcp 3.x
    "py-key-value-aio[disk]>=0.3.0",  # Explicitly requires disk extra
]
```

These constraints:
- ✅ Are included in the wheel metadata
- ✅ Are respected by all package installers (uvx, pip, poetry, etc.)
- ✅ Prevent breaking changes from transitive dependencies
- ✅ Follow standard Python packaging best practices

### When to Update `uv.lock`

Update the lock file whenever dependencies change:

```bash
# After modifying pyproject.toml dependencies
uv lock

# Verify the lock file is current
uv sync
```

The lock file ensures all developers use identical dependency versions, but remember: **end users will get versions based on `pyproject.toml` constraints, not the lock file**.
