#!/usr/bin/env python3
"""
UI build pipeline for Mohnitor.

Builds Next.js static output and embeds it in the Python package.
This script will be expanded in later tasks when UI components are implemented.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path


def main():
    """Build UI and embed in Python package."""
    repo_root = Path(__file__).parent.parent
    ui_dir = repo_root / "ui"
    ui_dist_dir = repo_root / "src" / "mohflow" / "devui" / "ui_dist"

    print("🔧 Mohnitor UI Build Pipeline")

    # Check if UI directory exists
    if not ui_dir.exists():
        print("⚠️  UI directory not found. Will be created in later tasks.")
        print(f"   Expected: {ui_dir}")

        # Create placeholder UI dist directory
        ui_dist_dir.mkdir(parents=True, exist_ok=True)

        # Create placeholder index.html
        placeholder_html = """<!DOCTYPE html>
<html>
<head>
    <title>Mohnitor - Coming Soon</title>
    <style>
        body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
        .container { max-width: 600px; margin: 0 auto; }
        .logo { font-size: 2em; color: #333; margin-bottom: 20px; }
        .message { color: #666; }
    </style>
</head>
<body>
    <div class="container">
        <div class="logo">📊 Mohnitor</div>
        <h1>Log Viewer Coming Soon</h1>
        <p class="message">
            The Mohnitor UI is being built. This placeholder will be replaced
            with the full Next.js application in upcoming tasks.
        </p>
    </div>
</body>
</html>"""

        with open(ui_dist_dir / "index.html", "w") as f:
            f.write(placeholder_html)

        print("✅ Created placeholder UI files")
        return True

    # Future implementation: Build Next.js app
    print("🚧 Full UI build pipeline will be implemented in T051-T058")
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)