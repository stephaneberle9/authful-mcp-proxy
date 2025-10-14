# Building Windows Executable with PyInstaller

This guide explains how to create a standalone Windows executable (.exe) for authful-mcp-proxy using PyInstaller.

## Prerequisites

- Python 3.10 or later installed on Windows
- Git (to clone the repository)
- Admin rights may be needed for some installations

## Quick Start (Windows)

1. **Clone the repository**:
   ```cmd
   git clone https://github.com/yourusername/authful-mcp-proxy.git
   cd authful-mcp-proxy
   ```

2. **Set up the virtual environment**:
   ```cmd
   python -m pip install uv
   uv venv
   bin\activate.bat
   uv sync
   ```

3. **Build the executable**:
   ```cmd
   build_windows.bat
   ```

4. **Find your executable**:
   The executable will be in `dist\authful-mcp-proxy.exe`

## Manual Build Steps

If you prefer to build manually or the automated script doesn't work:

1. **Activate virtual environment**:
   ```cmd
   bin\activate.bat
   ```

2. **Install PyInstaller**:
   ```cmd
   pip install pyinstaller
   ```

3. **Clean previous builds** (optional):
   ```cmd
   rmdir /s /q build
   rmdir /s /q dist
   ```

4. **Build the executable**:
   ```cmd
   pyinstaller --clean authful-mcp-proxy.spec
   ```

5. **Test the executable**:
   ```cmd
   dist\authful-mcp-proxy.exe --help
   ```

## Using the Windows Executable

### With Claude Desktop

Once built, you can use the executable directly in your Claude Desktop configuration:

```jsonc
{
  "mcpServers": {
    "my-protected-server": {
      "command": "C:\\path\\to\\authful-mcp-proxy.exe",
      "args": [
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

**Important Notes:**
- Use double backslashes (`\\`) in Windows paths
- Use the full absolute path to the .exe file
- Make sure the OIDC client has `http://localhost:8080/auth/callback` as an allowed redirect URI

### Standalone Usage

You can also run the executable directly from the command line:

```cmd
authful-mcp-proxy.exe ^
  --oidc-issuer-url https://auth.company.com ^
  --oidc-client-id your-client-id ^
  https://mcp-backend.company.com/mcp
```

## Customizing the Build

### Spec File Configuration

The [authful-mcp-proxy.spec](authful-mcp-proxy.spec) file controls the build process. Key sections:

- **`hiddenimports`**: Add any missing Python modules
- **`datas`**: Include additional data files
- **`excludes`**: Remove unnecessary packages to reduce size
- **`console=True`**: Must be True for MCP stdio communication

### Adding an Icon

To add a custom icon to your executable:

1. Create or obtain a `.ico` file
2. Edit `authful-mcp-proxy.spec` and change:
   ```python
   icon=None,  # Change to: icon='path/to/your/icon.ico'
   ```
3. Rebuild with `pyinstaller --clean authful-mcp-proxy.spec`

### Reducing Executable Size

The executable is ~8-10 MB. To reduce size:

1. **Remove UPX compression** (if causing issues):
   ```python
   upx=False,  # In the spec file
   ```

2. **Exclude more packages**:
   ```python
   excludes=[
       'tkinter',
       'matplotlib',
       'numpy',
       'pandas',
       'test',
       'unittest',
   ],
   ```

## Troubleshooting

### Build Fails with "Module Not Found"

Add the missing module to `hiddenimports` in the spec file:
```python
hiddenimports=[
    'your_missing_module',
    # ... other imports
],
```

### Executable Doesn't Run on Other Windows Machines

Make sure you're building on the oldest Windows version you want to support. Executables built on newer Windows versions may not work on older ones.

Alternatively, install the Microsoft Visual C++ Redistributable on the target machine.

### "Access Denied" or Antivirus Warnings

Some antivirus software flags PyInstaller executables as suspicious. To fix:
1. Add an exception in your antivirus for the executable
2. Code sign the executable (requires a code signing certificate)
3. Upload the executable to VirusTotal and wait for AV vendors to whitelist it

### Executable is Too Large

- Remove unnecessary dependencies from the spec file's `excludes` list
- Use `--onefile` mode (creates a larger exe but no separate folder)
- Strip debug symbols (already done by default)

### Testing Without Windows

You cannot cross-compile Windows executables on macOS/Linux with PyInstaller. You need:
- A Windows machine or VM
- Wine (on Linux, experimental)
- Windows in Docker (limited support)

## Distribution

### Single File Distribution

The current configuration creates a single-file executable (`--onefile` mode) that includes all dependencies. Simply distribute `dist\authful-mcp-proxy.exe`.

### Folder Distribution

If you prefer faster startup time, modify the spec file to use folder mode:
```python
# Comment out or remove the '--onefile' behavior by using separate EXE/COLLECT
```

Then distribute the entire `dist\authful-mcp-proxy\` folder.

## Security Considerations

1. **Code Signing**: Consider signing the executable to avoid security warnings
2. **Credentials**: The executable will store OIDC tokens in `%USERPROFILE%\.fastmcp\oauth-mcp-client-cache\`
3. **Source Code**: The Python source code is embedded but somewhat obfuscated in the executable

## Advanced Options

### Debug Build

To create a debug build with console output:
```cmd
pyinstaller --clean --debug all authful-mcp-proxy.spec
```

### Custom Python Environment

If you need a specific Python version:
```cmd
C:\Python310\python.exe -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
pyinstaller authful-mcp-proxy.spec
```

## Getting Help

- Check the [PyInstaller documentation](https://pyinstaller.org/)
- Review the [main README](README.md) for usage instructions
- Open an issue on GitHub with build errors

## License

This build configuration is part of authful-mcp-proxy and follows the same license as the main project.
