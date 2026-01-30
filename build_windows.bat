@echo off
REM Build script for creating Windows executable with PyInstaller
REM
REM This script:
REM 1. Activates the virtual environment
REM 2. Installs PyInstaller if needed
REM 3. Builds the Windows executable using the spec file
REM 4. Reports the output location

echo ========================================
echo Building authful-mcp-proxy for Windows
echo ========================================
echo.

REM Check if virtual environment exists
if exist ".venv\Scripts\activate.bat" (
    set VENV_ACTIVATE=.venv\Scripts\activate.bat
) else if exist "bin\activate.bat" (
    set VENV_ACTIVATE=bin\activate.bat
) else (
    echo ERROR: Virtual environment not found!
    echo Please run: uv venv
    echo Then run: .venv\Scripts\activate.bat
    echo Then run: uv sync
    exit /b 1
)

REM Activate virtual environment
echo Activating virtual environment from %VENV_ACTIVATE%...
call %VENV_ACTIVATE%

REM Check if PyInstaller is installed
python -c "import PyInstaller" 2>nul
if errorlevel 1 (
    echo PyInstaller not found. Installing...
    where uv >nul 2>nul
    if errorlevel 1 (
        python -m pip install pyinstaller
    ) else (
        uv pip install pyinstaller
    )
)

REM Clean previous build artifacts
echo.
echo Cleaning previous build artifacts...
if exist "build" rmdir /s /q build
if exist "dist" rmdir /s /q dist

REM Build the executable
echo.
echo Building executable with PyInstaller...
pyinstaller --clean authful-mcp-proxy.spec

REM Check if build was successful
if exist "dist\authful-mcp-proxy.exe" (
    echo.
    echo ========================================
    echo Build completed successfully!
    echo ========================================
    echo Executable location: dist\authful-mcp-proxy.exe
    echo.
    echo You can now:
    echo 1. Copy dist\authful-mcp-proxy.exe to your desired location
    echo 2. Configure it in Claude Desktop like:
    echo.
    echo    "command": "C:\\path\\to\\authful-mcp-proxy.exe",
    echo    "args": ["https://your-mcp-backend.com/mcp"],
    echo    "env": {
    echo      "OIDC_ISSUER_URL": "https://your-auth-server.com",
    echo      "OIDC_CLIENT_ID": "your-client-id"
    echo    }
    echo.
) else (
    echo.
    echo ========================================
    echo Build FAILED!
    echo ========================================
    echo Please check the error messages above.
    exit /b 1
)
