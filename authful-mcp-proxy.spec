# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for authful-mcp-proxy Windows executable.

This spec file creates a standalone executable for Windows that includes:
- All Python dependencies (fastmcp, httpx, etc.)
- Hidden imports for OIDC and async libraries
- Proper console configuration for MCP stdio communication
"""

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

# Get the project root directory
block_cipher = None
project_root = os.path.abspath(SPECPATH)

# Collect hidden imports for fastmcp and related packages
hiddenimports = [
    'authful_mcp_proxy',
    'authful_mcp_proxy.__main__',
    'authful_mcp_proxy.__init__',
    'authful_mcp_proxy.config',
    'authful_mcp_proxy.external_oidc',
    'authful_mcp_proxy.mcp_proxy',
    'fastmcp',
    'httpx',
    'httpx._client',
    'httpx._config',
    'httpx._models',
    'httpcore',
    'h11',
    'certifi',
    'asyncio',
    'json',
    'webbrowser',
    'urllib.parse',
    'base64',
    'hashlib',
    'secrets',
    'pathlib',
    'importlib.metadata',
    'logging',
    'argparse',
]

# Collect all submodules from fastmcp (may have hidden dependencies)
hiddenimports.extend(collect_submodules('fastmcp'))
hiddenimports.extend(collect_submodules('httpx'))

# Collect data files from packages if needed
datas = []
datas += collect_data_files('fastmcp', include_py_files=True)
# Copy package metadata for version detection
datas += copy_metadata('fastmcp')
datas += copy_metadata('authful-mcp-proxy', recursive=True)
datas += copy_metadata('httpx')
datas += copy_metadata('mcp')

a = Analysis(
    ['run_proxy.py'],
    pathex=[os.path.join(project_root, 'src')],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'numpy',
        'pandas',
        'IPython',
        'jupyter',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='authful-mcp-proxy',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Must be True for MCP stdio communication
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add .ico file path here if you have an icon
)
