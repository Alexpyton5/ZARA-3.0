"""Explicit isolated Lab canary; never enables general desktop/voice actions."""
import os
from pathlib import Path
import tempfile

READ_CHANNELS = frozenset({'lab-v1-snapshot', 'lab-v1-providers'})
LIVE_CHANNELS = frozenset({'lab-v1-autopilot', 'lab-v1-cancel-mission'})


def allowed(channel):
    if channel in READ_CHANNELS:
        return True
    if channel not in LIVE_CHANNELS or os.environ.get('ZARA_LAB_LIVE_CANARY') != '1':
        return False
    home = os.environ.get('ZARA3_HOME')
    if not home:
        return False
    target = Path(home).resolve()
    root = (Path(tempfile.gettempdir()) / 'zara-lab-canaries').resolve()
    return root in target.parents and (target / 'CANARY_ONLY').is_file()
