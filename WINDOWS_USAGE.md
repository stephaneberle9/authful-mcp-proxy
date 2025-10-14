# Windows Executable Usage Guide

Quick reference for using the pre-built Windows executable of authful-mcp-proxy.

## Download

Get the latest Windows executable from:

- GitHub Releases page (if available)
- Build it yourself following [BUILD_WINDOWS.md](BUILD_WINDOWS.md)

## Quick Setup

### 1. Place the Executable

Copy `authful-mcp-proxy.exe` to a permanent location, for example:

```
C:\Program Files\authful-mcp-proxy\authful-mcp-proxy.exe
```

Or a user directory:

```
C:\Users\YourName\Tools\authful-mcp-proxy.exe
```

### 2. Configure Claude Desktop

Open Claude Desktop settings:

- Click **Settings** → **Developer** → **Edit Config**

Add your server configuration:

```jsonc
{
  "mcpServers": {
    "my-server": {
      "command": "C:\\Program Files\\authful-mcp-proxy\\authful-mcp-proxy.exe",
      "args": ["https://your-mcp-backend.com/mcp"],
      "env": {
        "OIDC_ISSUER_URL": "https://your-auth-server.com",
        "OIDC_CLIENT_ID": "your-client-id",
      },
    },
  },
}
```

**Important:**

- Use double backslashes (`\\`) in paths
- Use the full absolute path to the executable
- Configure your OIDC client with redirect URI: `http://localhost:8080/auth/callback`

### 3. Restart Claude Desktop

Close and reopen Claude Desktop to load the new configuration.

### 4. First Run

On first use:

1. Claude Desktop will launch the proxy
2. Your browser will open for authentication
3. Sign in to your OIDC provider
4. Approve the requested scopes
5. Return to Claude Desktop

Your credentials will be cached in:

```
C:\Users\YourName\.fastmcp\oauth-mcp-client-cache\
```

## Command Line Usage

You can also run the executable directly:

```cmd
authful-mcp-proxy.exe --help
```

### Basic Example

```cmd
authful-mcp-proxy.exe ^
  --oidc-issuer-url https://auth.example.com ^
  --oidc-client-id my-client-id ^
  https://mcp.example.com/mcp
```

### With Client Secret

```cmd
authful-mcp-proxy.exe ^
  --oidc-issuer-url https://auth.example.com ^
  --oidc-client-id my-client-id ^
  --oidc-client-secret my-secret ^
  --oidc-scopes "openid profile email api:access" ^
  https://mcp.example.com/mcp
```

### Debug Mode

```cmd
authful-mcp-proxy.exe --debug https://mcp.example.com/mcp
```

## Configuration Options

### Environment Variables

Set these in your system or in the `env` block of your Claude Desktop config:

| Variable             | Required | Default                               | Description                          |
| -------------------- | -------- | ------------------------------------- | ------------------------------------ |
| `MCP_BACKEND_URL`    | Yes\*    | -                                     | Backend MCP server URL               |
| `OIDC_ISSUER_URL`    | Yes      | -                                     | OIDC issuer URL                      |
| `OIDC_CLIENT_ID`     | Yes      | -                                     | OAuth client ID                      |
| `OIDC_CLIENT_SECRET` | No       | -                                     | OAuth client secret                  |
| `OIDC_SCOPES`        | No       | `openid profile email`                | Space-separated scopes               |
| `OIDC_REDIRECT_URL`  | No       | `http://localhost:8080/auth/callback` | OAuth redirect URL                   |
| `MCP_PROXY_DEBUG`    | No       | `0`                                   | Enable debug logging (1/true/yes/on) |

\* Can be provided as first command-line argument instead

### Command-Line Flags

```
authful-mcp-proxy.exe [OPTIONS] <MCP_BACKEND_URL>

Options:
  --oidc-issuer-url URL      OIDC issuer URL
  --oidc-client-id ID        OAuth client ID
  --oidc-client-secret SEC   OAuth client secret (optional)
  --oidc-scopes SCOPES       Space-separated OAuth scopes
  --oidc-redirect-url URL    OAuth redirect URL
  --no-banner                Don't show startup banner
  --silent                   Show only errors
  --debug                    Enable debug logging
  --help                     Show help message
```

## Common Issues

### "Windows protected your PC"

Windows SmartScreen may block unsigned executables:

1. Click **More info**
2. Click **Run anyway**

To avoid this permanently:

- Code sign the executable (requires certificate)
- Add to Windows Defender exclusions

### Browser Doesn't Open

1. Check if port 8080 is available
2. Manually open the URL shown in logs
3. Check firewall settings

### "The system cannot find the path specified"

1. Verify the executable path is correct
2. Use absolute paths, not relative
3. Use double backslashes in JSON: `C:\\path\\to\\file.exe`

### 401 Unauthorized

1. Verify OIDC configuration is correct
2. Check scopes are approved
3. Clear cached credentials:
   ```cmd
   rmdir /s "%USERPROFILE%\.fastmcp\oauth-mcp-client-cache"
   ```
4. Try again with `--debug` flag

### Antivirus Blocks Execution

1. Add executable to antivirus exclusions
2. Use a different antivirus that doesn't flag PyInstaller executables
3. Build from source on your own machine

## Updating

To update to a new version:

1. Download/build the new executable
2. Stop Claude Desktop
3. Replace the old .exe file
4. Restart Claude Desktop

Your cached credentials will be preserved.

## Uninstalling

1. Stop Claude Desktop
2. Remove the executable file
3. Remove from Claude Desktop config
4. (Optional) Delete cached credentials:
   ```cmd
   rmdir /s "%USERPROFILE%\.fastmcp\oauth-mcp-client-cache"
   ```

## Security Notes

### Credential Storage

OAuth tokens are stored in:

```
%USERPROFILE%\.fastmcp\oauth-mcp-client-cache\
```

These files contain sensitive access tokens. Protect them:

- Don't share these files
- Don't commit them to version control
- Use Windows file permissions to restrict access

### HTTPS Required

Always use HTTPS URLs for:

- MCP backend servers
- OIDC issuer URLs
- OAuth redirect URLs (except localhost)

### Client Secrets

If using a client secret:

- Don't hardcode in config files that are shared
- Use Windows environment variables
- Consider using Windows Credential Manager

## Getting Help

- Full documentation: [README.md](README.md)
- Build instructions: [BUILD_WINDOWS.md](BUILD_WINDOWS.md)
- GitHub Issues: Report bugs and ask questions

## Example Configurations

### Keycloak

```jsonc
{
  "command": "C:\\Tools\\authful-mcp-proxy.exe",
  "args": ["https://api.example.com/mcp"],
  "env": {
    "OIDC_ISSUER_URL": "https://keycloak.example.com/realms/myrealm",
    "OIDC_CLIENT_ID": "mcp-client",
  },
}
```

### Azure AD / Entra ID

```jsonc
{
  "command": "C:\\Tools\\authful-mcp-proxy.exe",
  "args": ["https://api.example.com/mcp"],
  "env": {
    "OIDC_ISSUER_URL": "https://login.microsoftonline.com/{tenant-id}/v2.0",
    "OIDC_CLIENT_ID": "your-app-id",
    "OIDC_SCOPES": "openid profile email api://your-api/.default",
  },
}
```

### Auth0

```jsonc
{
  "command": "C:\\Tools\\authful-mcp-proxy.exe",
  "args": ["https://api.example.com/mcp"],
  "env": {
    "OIDC_ISSUER_URL": "https://your-domain.auth0.com",
    "OIDC_CLIENT_ID": "your-client-id",
    "OIDC_SCOPES": "openid profile email offline_access",
  },
}
```

### Okta

```jsonc
{
  "command": "C:\\Tools\\authful-mcp-proxy.exe",
  "args": ["https://api.example.com/mcp"],
  "env": {
    "OIDC_ISSUER_URL": "https://your-domain.okta.com/oauth2/default",
    "OIDC_CLIENT_ID": "your-client-id",
  },
}
```
