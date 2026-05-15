<!-- omit from toc -->
Authsome MCP Proxy
==================

A [Model Context Protocol](https://modelcontextprotocol.com) (MCP) proxy server that performs OIDC authentication to obtain access tokens for remote MCP servers protected by token validation. It can run in two modes:

- **Local stdio proxy** — launched as a subprocess by an MCP client (Claude Desktop, Cursor, Codex, Claude Code via `claude mcp add --transport stdio`). Each client manages its own proxy instance.
- **Web connector proxy** — runs as a persistent HTTP server, shared by any number of MCP clients that connect by URL (e.g. Claude Code via `claude mcp add --transport http`).

- [What Is This For?](#what-is-this-for)
  - [Technical Background](#technical-background)
- [Usage](#usage)
  - [Prerequisites](#prerequisites)
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
    - [Example 7: Web Connector Proxy (HTTP Transport)](#example-7-web-connector-proxy-http-transport)
  - [Using with Other MCP Clients](#using-with-other-mcp-clients)
    - [Claude Code](#claude-code)
    - [MCP Inspector](#mcp-inspector)
    - [Cursor / Codex](#cursor--windsurf)
    - [Command Line / Direct Usage](#command-line--direct-usage)
  - [Credential Management](#credential-management)
    - [Where Are Credentials Stored?](#where-are-credentials-stored)
    - [Clear Cached Credentials](#clear-cached-credentials)
  - [Troubleshooting](#troubleshooting)
    - [Browser Doesn't Open for Authentication](#browser-doesnt-open-for-authentication)
    - [Authentication Fails in Headless / Server Environments](#authentication-fails-in-headless--server-environments)
    - [401 Unauthorized Errors](#401-unauthorized-errors)
    - [Redirect URI Mismatch](#redirect-uri-mismatch)
    - [Token Refresh Failures](#token-refresh-failures)
    - [Connection to Upstream Fails](#connection-to-upstream-fails)
    - [MCP Client Doesn't Recognize the Proxy](#mcp-client-doesnt-recognize-the-proxy)
    - [Debug Logging](#debug-logging)
    - [Still Having Issues?](#still-having-issues)
- [Contributing](#contributing)

# What Is This For?

Use `authsome-mcp-proxy` when you need to connect MCP clients to a remote MCP server that:

- Is protected by OAuth/OIDC token validation
- Doesn't handle authentication itself (no built-in OAuth flows)
- Returns `401 Unauthorized` without proper access tokens

**As a local stdio proxy** (default), it is launched as a subprocess by the MCP client. Each user runs their own instance. Supported by Claude Desktop, Cursor, Codex, and Claude Code (`claude mcp add --transport stdio`).

**As a web connector proxy** (`--transport http`), it runs as a persistent HTTP server. A single instance can serve multiple clients simultaneously, each getting an isolated upstream session. Useful for shared team deployments or anywhere a URL endpoint is more practical than a per-user subprocess. Connect with Claude Code via `claude mcp add --transport http <name> <url>`.

The proxy handles the full OIDC authentication flow, securely stores credentials in `~/.mcp-auth/authsome-mcp-proxy-<version>/`, and automatically refreshes tokens as needed.

## Technical Background

Typically, securing MCP connections with OAuth or OpenID connect (OIDC) requires "authful" MCP servers that [coordinate with external identity providers](https://gofastmcp.com/servers/auth/authentication#external-identity-providers). MCP clients handle authentication through the MCP server, which in turn interacts with the OAuth or OIDC authorization server. However, this doesn't work with MCP servers only protected by [token validation](https://gofastmcp.com/servers/auth/authentication#token-validation), i.e., MCP servers that trust tokens from a known issuer but don't coordinate with the OAuth/OIDC authorization server themselves. In such scenarios, MCP clients detect the MCP server isn't authful and skip the OAuth/OIDC authentication entirely, resulting in `401 Unauthorized` errors for all tool, resource, and prompt requests.

This MCP proxy fills that gap by handling authentication independently through direct OIDC authorization server interaction. It performs the OAuth authorization code flow by opening the user's browser to the OIDC authorization endpoint for login and scope approval. A temporary local HTTP server receives the OAuth redirect and exchanges the authorization code for access and refresh tokens using PKCE. The access token is used as a Bearer token for all upstream MCP server requests and cached locally to avoid repeated browser interactions. When tokens expire, the proxy automatically obtains new ones using the refresh token.

# Usage

## Prerequisites

This tool requires `uvx` (part of [uv](https://docs.astral.sh/uv/)). Install it via:

```bash
# Windows
winget install --id=astral-sh.uv -e

# macOS
brew install uv

# Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

> **macOS note:** The `curl` installer places `uv` in `~/.local/bin/` and updates your shell profile, but macOS GUI apps like Claude Desktop do not load shell startup files. This means Claude Desktop won't find `uv` even though it works in your terminal. Installing via Homebrew avoids this entirely since it places `uv` in `/opt/homebrew/bin/` (Apple Silicon) or `/usr/local/bin/` (Intel), which GUI apps can see. If you already installed `uv` via `curl`, either reinstall with `brew install uv` or symlink it: `sudo ln -s ~/.local/bin/uv /usr/local/bin/uv`

See the [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/) for more options.

## Quick Start

The simplest way to use `authsome-mcp-proxy` with MCP clients like Claude Desktop:

```jsonc
{
  "mcpServers": {
    "my-protected-server": {
      "command": "uvx",
      "args": [
        "authsome-mcp-proxy",
        "https://mcp-upstream.company.com/mcp"
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

All options can be set via environment variables in the `env` block or passed as CLI arguments (see `uvx authsome-mcp-proxy --help`).

### Required Configuration

| Environment Variable | Description | Example |
|---------------------|-------------|---------|
| `UPSTREAM_MCP_URL` | Remote MCP server URL (can also be first argument) | `https://mcp.example.com/mcp` |
| `OIDC_ISSUER_URL` | Your OIDC provider's issuer URL | `https://auth.example.com` |
| `OIDC_CLIENT_ID` | OAuth client ID from your OIDC provider | `my-app-client-id` |

### Optional Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `OIDC_CLIENT_SECRET` | _(none)_ | Client secret (not needed for public clients that don't require any such) |
| `OIDC_SCOPES` | `openid profile email` | Space-separated OAuth scopes. Add `offline_access` for providers like Keycloak, Auth0, or Okta for silent token refresh avoiding repeated browser-based auth flows. **Not needed for AWS Cognito** (issues refresh tokens automatically). |
| `OIDC_REDIRECT_URL` | `http://localhost:8080/auth/callback` | OAuth callback URL |

### Advanced Options

| CLI Flag / Env Var | Description |
|--------------------|-------------|
| `--transport {stdio,http}` / `MCP_PROXY_TRANSPORT` | Transport to serve on. `stdio` (default): launched as a local process by the MCP client. `http`: runs as a standalone HTTP server. |
| `--host` / `MCP_PROXY_HOST` | Host address to bind to for HTTP transport (default: `0.0.0.0`) |
| `--port` / `MCP_PROXY_PORT` | Port to listen on for HTTP transport (default: `8000`) |
| `--no-banner` | Suppress the startup banner |
| `--silent` | Show only error messages |
| `--debug` / `MCP_PROXY_DEBUG` | Enable detailed debug logging |

## Usage Examples

### Example 1: Claude Desktop (Recommended)

Add to your Claude Desktop config (accessible via Settings → Developer → Edit Config):

```jsonc
{
  "mcpServers": {
    "company-tools": {
      "command": "uvx",
      "args": [
        "authsome-mcp-proxy",
        "https://mcp-upstream.company.com/mcp"
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
        "authsome-mcp-proxy@latest",
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
      "args": ["authsome-mcp-proxy", "https://api.example.com/mcp"],
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
      "args": ["authsome-mcp-proxy", "https://mcp.example.com"],
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
        "/path/to/authsome-mcp-proxy",
        "authsome-mcp-proxy",
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
        "authsome-mcp-proxy",
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

### Example 7: Web Connector Proxy (HTTP Transport)

Run the proxy as a persistent HTTP server that any MCP client can reach by URL. Useful for shared team deployments or when a URL endpoint is more practical than a per-user subprocess.

**Step 1 — Start the proxy** on any machine with a browser (needed for first-time OIDC authentication):

```bash
uvx authsome-mcp-proxy \
  --transport http \
  --host 0.0.0.0 \
  --port 8000 \
  --oidc-issuer-url https://auth.example.com \
  --oidc-client-id my-client-id \
  https://mcp-upstream.example.com/mcp
```

Or equivalently via environment variables (useful for Docker or systemd):

```bash
MCP_PROXY_TRANSPORT=http \
MCP_PROXY_PORT=8000 \
OIDC_ISSUER_URL=https://auth.example.com \
OIDC_CLIENT_ID=my-client-id \
UPSTREAM_MCP_URL=https://mcp-upstream.example.com/mcp \
uvx authsome-mcp-proxy
```

The proxy will open a browser for OIDC login on first run, then cache the tokens and start the HTTP server at `http://0.0.0.0:8000/mcp`.

> ⚠️ **Important:** Make sure your OIDC client is configured with `http://localhost:8080/auth/callback` as an allowed redirect URI!
>
> ℹ️ **Note:** If deploying to a headless server, see [Authentication Fails in Headless / Server Environments](#authentication-fails-in-headless--server-environments) for how to handle first-time authentication.

**Step 2 — Connect clients** to the running proxy by URL. Each client gets an isolated upstream session.

With Claude Code:
```bash
claude mcp add --transport http my-server http://your-proxy-host:8000/mcp
```

With MCP Inspector:
```bash
npx @modelcontextprotocol/inspector http://your-proxy-host:8000/mcp
```

## Using with Other MCP Clients

### Claude Code

Claude Code supports both stdio and HTTP transport. Use stdio if you want each developer to run their own proxy instance; use HTTP if you have a shared proxy running as a server.

**Stdio (per-user process, launched by Claude Code):**

```bash
claude mcp add --transport stdio my-server -- \
  uvx authsome-mcp-proxy \
  --oidc-issuer-url https://auth.example.com \
  --oidc-client-id my-client-id \
  https://mcp-upstream.example.com/mcp
```

**HTTP (connecting to a running proxy by URL):**

```bash
claude mcp add --transport http my-server http://proxy-host:8000/mcp
```

Both commands default to project scope (stored in `.mcp.json`). Add `--scope user` to make the server available across all your projects.

### MCP Inspector

**Stdio (proxy launched by the inspector):**

Create an `mcp.json` file:

```jsonc
{
  "mcpServers": {
    "authsome-mcp-proxy": {
      "command": "uvx",
      "args": ["authsome-mcp-proxy", "https://mcp.example.com/mcp"],
      "env": {
        "OIDC_ISSUER_URL": "https://auth.example.com",
        "OIDC_CLIENT_ID": "inspector-client"
      }
    }
  }
}
```

> ⚠️ **Important:** Make sure your OIDC client is configured with `http://localhost:8080/auth/callback` as an allowed redirect URI!

```bash
npx @modelcontextprotocol/inspector --config mcp.json --server authsome-mcp-proxy
```

**HTTP (connecting to a running proxy):**

```bash
npx @modelcontextprotocol/inspector http://localhost:8000/mcp
```

### Cursor / Codex

These editors use the same configuration format as Claude Desktop. Add the server config to your MCP settings file.

### Command Line / Direct Usage

```bash
# Install globally
uvx authsome-mcp-proxy --help

# Run directly
uvx authsome-mcp-proxy \
  --oidc-issuer-url https://auth.example.com \
  --oidc-client-id my-client \
  https://mcp.example.com/mcp
```

## Credential Management

### Where Are Credentials Stored?

Credentials are cached in `~/.mcp-auth/authsome-mcp-proxy-<version>/` (where `<version>` is the installed package version, e.g. `0.5.0`) as a SQLite database:
```
~/.mcp-auth/authsome-mcp-proxy-0.5.0/
  ├── cache.db
  ├── cache.db-shm
  └── cache.db-wal
```

### Clear Cached Credentials

To force re-authentication (e.g., to switch accounts or clear expired tokens):

```bash
# Linux/macOS
rm -rf ~/.mcp-auth/authsome-mcp-proxy*

# Windows
rmdir /s %USERPROFILE%\.mcp-auth\authsome-mcp-proxy*
```

The next time you connect, you'll be prompted to authenticate again.

## Troubleshooting

### Browser Doesn't Open for Authentication

**Problem:** The proxy starts but no browser window opens.

**Solutions:**
1. Check that port 8080 (or your custom redirect port) isn't blocked
2. Manually open the URL shown in the proxy logs
3. Verify your firewall isn't blocking localhost connections

### Authentication Fails in Headless / Server Environments

**Problem:** Running the proxy as an HTTP server on a headless machine (Docker container, cloud VM, CI) where no browser is available for the initial OIDC login.

**Solution:** Authenticate once on a machine with a browser, then copy the token cache to the server.

1. On your local machine, run the proxy with the same OIDC config to trigger the browser login:

   ```bash
   uvx authsome-mcp-proxy \
     --oidc-issuer-url https://auth.example.com \
     --oidc-client-id my-client-id \
     https://mcp-upstream.example.com/mcp
   ```

2. After successful login, copy the token cache to the server:

   ```bash
   # Linux/macOS — copy the whole versioned directory
   scp -r ~/.mcp-auth/authsome-mcp-proxy-<version> user@server:~/.mcp-auth/
   ```

3. Start the proxy on the server — it will pick up the cached tokens and skip the browser flow.

Tokens will be silently refreshed using the refresh token for as long as the refresh token remains valid (typically days to weeks depending on your OIDC provider). Add `offline_access` to `OIDC_SCOPES` for providers like Keycloak, Auth0, and Okta to get long-lived refresh tokens.

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

**Problem:** Proxy works initially but fails after some time, or browser opens repeatedly (hourly) for re-authentication.

**Solutions:**
1. Check if your OIDC provider issued a refresh token (some providers don't for certain grant types)
2. **For Keycloak, Auth0, Okta:** Add `offline_access` to `OIDC_SCOPES` to enable refresh tokens:
   ```
   "OIDC_SCOPES": "openid profile email offline_access"
   ```
3. **For AWS Cognito:** Refresh tokens are issued automatically - verify your app client has "Authorization code grant" enabled in the Cognito console
4. Clear cached credentials to get new tokens: `rm -rf ~/.mcp-auth/authsome-mcp-proxy*/`

### Connection to Upstream Fails

**Problem:** Can't connect to remote MCP server.

**Solutions:**
1. Verify the upstream URL is correct and accessible
2. Check network connectivity to the upstream server
3. Ensure the upstream server is running and accepting connections
4. Try accessing the upstream URL directly in a browser to verify it's reachable
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
uvx authsome-mcp-proxy --debug https://mcp.example.com/mcp
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

1. Check the [examples directory](examples/token_validating_upstream_mcp/) for a working test setup
2. Run with `--debug` to get detailed logs
3. Verify your OIDC provider configuration
4. Open an issue on GitHub with debug logs (redact sensitive information)

# Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing, CI/CD workflows, and release process.

