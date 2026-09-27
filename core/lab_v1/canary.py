"""Explicit isolated Lab canary; never enables general desktop/voice actions."""
import os
from pathlib import Path

READ_CHANNELS = frozenset({'lab-state', 'lab-v1-snapshot', 'lab-v1-providers'})
LIVE_CHANNELS = frozenset({
    # Current Electron contract.  A Lab mutation is durably admitted and then
    # confirmed; the backend consumer performs the actual submit/cancel.
    'lab-v1-admit-operation',
    'lab-v1-confirm-operation',
    # Kept for direct/older canary clients that still call these channels.
    'lab-v1-autopilot',
    'lab-v1-cancel-mission',
})


def allowed(channel):
    if channel in READ_CHANNELS:
        return True
    if channel not in LIVE_CHANNELS:
        return False
    # The disposable home plus its marker is the execution authority. Electron
    # reliably forwards ZARA_SMOKE_TEST to the frozen sidecar, but auxiliary
    # environment switches are not a sound package-boundary proof. A marker
    # created only by electron_lab_canary.py is both stricter and reproducible.
    home = os.environ.get('ZARA3_HOME')
    if not home:
        return False
    target = Path(home).resolve()
    # PyInstaller and Electron may disagree about the process temp root while
    # the one-file sidecar is extracted. The harness authority is the exact
    # immediate parent plus the marker, both created before Electron starts.
    return target.parent.name == 'zara-lab-canaries' and (target / 'CANARY_ONLY').is_file()
