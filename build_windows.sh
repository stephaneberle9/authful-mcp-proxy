#!/bin/bash
# Build script for creating Windows executable with PyInstaller
#
# This script:
# 1. Activates the virtual environment
# 2. Installs PyInstaller if needed
# 3. Builds the Windows executable using the spec file
# 4. Reports the output location

set -e

echo "========================================"
echo "Building authful-mcp-proxy for Windows"
echo "========================================"
echo

# Check if virtual environment exists
if [ -f ".venv/bin/activate" ]; then
    VENV_ACTIVATE=".venv/bin/activate"
elif [ -f "bin/activate" ]; then
    VENV_ACTIVATE="bin/activate"
else
    echo "ERROR: Virtual environment not found!"
    echo "Please run: uv venv"
    echo "Then run: source .venv/bin/activate"
    echo "Then run: uv sync"
    exit 1
fi

# Activate virtual environment
echo "Activating virtual environment from $VENV_ACTIVATE..."
source "$VENV_ACTIVATE"

# Check if PyInstaller is installed
if ! python -c "import PyInstaller" 2>/dev/null; then
    echo "PyInstaller not found. Installing..."
    if command -v uv &> /dev/null; then
        uv pip install pyinstaller
    else
        python -m pip install pyinstaller
    fi
fi

# Clean previous build artifacts
echo
echo "Cleaning previous build artifacts..."
rm -rf build dist

# Build the executable
echo
echo "Building executable with PyInstaller..."
pyinstaller --clean authful-mcp-proxy.spec

# Check if build was successful
if [ -f "dist/authful-mcp-proxy.exe" ] || [ -f "dist/authful-mcp-proxy" ]; then
    echo
    echo "========================================"
    echo "Build completed successfully!"
    echo "========================================"
    if [ -f "dist/authful-mcp-proxy.exe" ]; then
        echo "Executable location: dist/authful-mcp-proxy.exe"
    else
        echo "Executable location: dist/authful-mcp-proxy"
    fi
    echo
    echo "You can now:"
    echo "1. Copy the executable to your desired location"
    echo "2. Configure it in Claude Desktop like:"
    echo
    echo '   "command": "C:\\path\\to\\authful-mcp-proxy.exe",'
    echo '   "args": ["https://your-mcp-backend.com/mcp"],'
    echo '   "env": {'
    echo '     "OIDC_ISSUER_URL": "https://your-auth-server.com",'
    echo '     "OIDC_CLIENT_ID": "your-client-id"'
    echo '   }'
    echo
else
    echo
    echo "========================================"
    echo "Build FAILED!"
    echo "========================================"
    echo "Please check the error messages above."
    exit 1
fi
