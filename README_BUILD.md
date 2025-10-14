# Windows Executable Build Summary

This document summarizes the PyInstaller setup for building Windows executables of authful-mcp-proxy.

## Files Created

### 1. **authful-mcp-proxy.spec**
PyInstaller specification file that defines:
- Entry point: `run_proxy.py`
- All dependencies (fastmcp, httpx, httpcore, h11, certifi, etc.)
- Package metadata for version detection
- Console mode configuration (required for MCP stdio)
- Exclusions to reduce executable size

### 2. **run_proxy.py**
Simplified entry point script that:
- Handles both frozen (PyInstaller) and normal Python execution
- Properly configures sys.path for imports
- Calls the main() function from authful_mcp_proxy

### 3. **build_windows.bat**
Windows batch script that:
- Activates the virtual environment
- Installs PyInstaller if needed
- Cleans previous build artifacts
- Builds the executable
- Reports build status and usage instructions

### 4. **build_windows.sh**
Unix/macOS shell script (for cross-platform development):
- Same functionality as the .bat file
- Useful for developers on macOS/Linux

### 5. **BUILD_WINDOWS.md**
Comprehensive documentation covering:
- Prerequisites and installation
- Quick start and manual build instructions
- Usage with Claude Desktop and other MCP clients
- Customization options (icons, size optimization, etc.)
- Troubleshooting common issues
- Distribution and security considerations

### 6. **WINDOWS_USAGE.md**
User-friendly guide for end-users:
- Download and setup instructions
- Claude Desktop configuration examples
- Command-line usage
- Configuration options reference
- Common issues and solutions
- Provider-specific examples (Keycloak, Azure AD, Auth0, Okta)

## Building the Executable

### On Windows

```cmd
REM 1. Set up the environment
git clone <repository-url>
cd authful-mcp-proxy
python -m pip install uv
uv venv
.venv\Scripts\activate
uv sync
uv pip install pyinstaller

REM 2. Build the executable
build_windows.bat

REM Output: dist\authful-mcp-proxy.exe (~25MB)
```

### On macOS/Linux (for testing only)

**⚠️ Important**: PyInstaller does NOT support cross-compilation. Running the build script on macOS/Linux will create a macOS/Linux executable, **NOT a Windows .exe**.

```bash
# 1. Set up the environment
git clone <repository-url>
cd authful-mcp-proxy
python -m pip install uv
uv venv
source .venv/bin/activate
uv sync
uv pip install pyinstaller

# 2. Build the executable (creates macOS/Linux binary, not Windows .exe)
./build_windows.sh

# Output: dist/authful-mcp-proxy (macOS/Linux executable for testing only)
```

#### To Build Actual Windows .exe from macOS/Linux

Since PyInstaller cannot cross-compile, use one of these methods:

1. **GitHub Actions** (Recommended - see CI/CD section below)
2. **Windows Virtual Machine** (VirtualBox, Parallels, VMware)
3. **Cloud Windows Instance** (AWS EC2, Azure VM)
4. **Wine on Linux** (experimental, may fail with complex dependencies)

## Key Technical Details

### Dependencies Included
- **fastmcp**: MCP server framework
- **httpx**: HTTP client for backend communication
- **httpcore**: Low-level HTTP transport
- **h11**: HTTP/1.1 protocol implementation
- **certifi**: SSL certificates
- **cryptography**: Cryptographic operations for OIDC
- **authlib**: OAuth/OIDC client library
- **pydantic**: Data validation
- All Python standard library modules needed

### Package Metadata
The spec file includes metadata for:
- `fastmcp` - required for version detection
- `authful-mcp-proxy` - application version
- `httpx` - HTTP client metadata
- `mcp` - MCP protocol metadata

### Entry Point Strategy
Instead of using `src/authful_mcp_proxy/__main__.py` directly, we use `run_proxy.py`:
- Avoids issues with relative imports in frozen executables
- Properly handles `sys._MEIPASS` for PyInstaller temp directory
- Ensures the source path is correctly configured

### Executable Configuration
- **Console Mode**: `console=True` is required for MCP stdio communication
- **UPX Compression**: Enabled to reduce size (can be disabled if causing issues)
- **Single File**: Creates a single .exe with all dependencies bundled
- **Architecture**: Builds for the host architecture (x86_64 or ARM)

## Testing the Build

```bash
# Test help command
./dist/authful-mcp-proxy --help

# Test version
./dist/authful-mcp-proxy --version

# Test with minimal args (will fail authentication but validates imports)
./dist/authful-mcp-proxy --oidc-issuer-url https://example.com --oidc-client-id test https://example.com/mcp
```

## Distribution

### Files to Distribute
- **Single file**: `dist/authful-mcp-proxy.exe`
- **Documentation**: README.md, WINDOWS_USAGE.md

### Size
- Approximately 25 MB for the macOS build
- Windows build will be similar (20-30 MB)

### Requirements for End Users
- Windows 10 or later (or macOS for the Mac build)
- No Python installation required
- Network access for OIDC authentication
- Browser for OAuth flow

## Troubleshooting Build Issues

### Missing Modules
If you get `ModuleNotFoundError` when running the executable:
1. Add the module to `hiddenimports` in the spec file
2. Rebuild with `pyinstaller --clean authful-mcp-proxy.spec`

### Metadata Errors
If you get `PackageNotFoundError` for package metadata:
1. Add `copy_metadata('package-name')` to the spec file
2. Rebuild

### Import Errors
If relative imports fail:
1. Check that `run_proxy.py` is the entry point
2. Verify `pathex` includes the src directory
3. Ensure all modules are in `hiddenimports`

### Large Executable Size
To reduce size:
1. Add more packages to `excludes` list
2. Disable UPX: set `upx=False`
3. Use folder mode instead of onefile (modify spec)

## Notes for Windows Build

When building on actual Windows:
- Replace `.venv/bin/activate` with `.venv\Scripts\activate.bat`
- Use `pyinstaller` instead of `./build_windows.sh`
- The output will be `dist\authful-mcp-proxy.exe`
- Windows Defender may flag the executable initially
- Consider code signing for production distribution

## CI/CD Integration

### GitHub Actions (Recommended)

A complete GitHub Actions workflow has been created at [`.github/workflows/build-executable.yml`](.github/workflows/build-executable.yml).

This workflow:
- ✅ Builds executables for **Windows**, **macOS**, and **Linux**
- ✅ Runs on every push and pull request
- ✅ Tests the executable with `--help` command
- ✅ Uploads build artifacts (available for 90 days)
- ✅ Automatically creates GitHub Releases when you push a version tag

#### How to Use

1. **Enable the workflow** (it's already in your repo)
2. **Push a tag to create a release**:
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```
3. **Download artifacts**:
   - Go to Actions → Build Executables → Click on a run
   - Download `authful-mcp-proxy-windows`, `authful-mcp-proxy-macos`, or `authful-mcp-proxy-linux`

#### Manual Workflow Snippet

For custom CI/CD systems, here's a minimal example:

```yaml
- name: Build Windows Executable
  run: |
    python -m pip install uv
    uv venv
    .venv\Scripts\activate
    uv sync
    uv pip install pyinstaller
    pyinstaller --clean authful-mcp-proxy.spec

- name: Upload Artifact
  uses: actions/upload-artifact@v4
  with:
    name: authful-mcp-proxy-windows
    path: dist/authful-mcp-proxy.exe
```

## Version Management

The executable includes version information from git tags:
- Version is automatically detected from `importlib.metadata`
- Development versions show git commit hash
- Release versions show semantic version (e.g., "1.0.0")

## Security Considerations

1. **Code Signing**: Consider signing the executable for production
2. **Secrets**: Never embed OIDC client secrets in the executable
3. **Updates**: Provide a mechanism for users to update to new versions
4. **Antivirus**: Test with major antivirus software
5. **Credentials**: Stored in `%USERPROFILE%\.fastmcp\oauth-mcp-client-cache\`

## Support

For issues or questions:
- Check [BUILD_WINDOWS.md](BUILD_WINDOWS.md) for detailed instructions
- Review [WINDOWS_USAGE.md](WINDOWS_USAGE.md) for user guidance
- Check the main [README.md](README.md) for general documentation
- Open an issue on GitHub
