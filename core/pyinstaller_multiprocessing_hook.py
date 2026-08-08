"""PyInstaller runtime hook for spawn-based research isolation on Windows."""
from __future__ import annotations

import multiprocessing

# Runtime hooks execute before main.py.  PyInstaller's freeze_support override
# consumes worker command-line arguments and prevents a spawned child from
# entering the sidecar's normal IPC main loop.
multiprocessing.freeze_support()
