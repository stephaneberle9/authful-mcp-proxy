#!/usr/bin/env python
"""
Entry point script for PyInstaller.

This script serves as the main entry point for the frozen executable,
avoiding issues with relative imports in __main__.py.
"""

import sys
import os

# Ensure the src directory is in the path for frozen executables
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    application_path = sys._MEIPASS
else:
    # Running as script
    application_path = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(application_path, 'src'))

# Import and run the main function
from authful_mcp_proxy.__main__ import main

if __name__ == "__main__":
    main()