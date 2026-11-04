"""Test settings. The app opens on Home for everyone; most screen tests start on "New case"."""

import os

os.environ.setdefault("RAAHI_START_SCREEN", "New case")
