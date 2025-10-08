"""Authful MCP proxy."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("authful_mcp_proxy")
except PackageNotFoundError:
    # If the package is not installed, use a development version
    __version__ = "0.0.0-dev"
