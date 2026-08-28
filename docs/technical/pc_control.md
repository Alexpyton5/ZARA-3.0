# PC Control in ZARA 3.0

## Overview

PC Control in ZARA 3.0 refers to the set of capabilities that allow the agent to interact with and control the user's personal computer. These capabilities are gated behind the `PC_CONTROL` and `LOCAL_PC_CONTROL` capability strings, which are checked before execution to ensure appropriate authorization.

## Capability Categories

ZARA distinguishes between two levels of PC control:

1. **PC_CONTROL** - Actions that interact with external systems or require broader system access (e.g., opening URLs in browsers, performing web searches)
2. **LOCAL_PC_CONTROL** - Actions that affect only the local machine in a more contained way (e.g., controlling media playback, opening known safe folders, adjusting system volume/brightness)

## Implementation Details

### Capability Checking
Actions declare their required capability using the `@action` decorator from `core.action_registry`:
```python
@action(name="browser_open_url", category="os", description="Open a validated HTTP(S) URL in the default browser", capability="PC_CONTROL")
def browser_open_url_action(url: str) -> ActionResult:
    # implementation
```

### Security Measures
- PC_CONTROL actions are subject to additional validation and hardening
- The system implements "PC-CONTROL-POLICY-HARDENING" to never expose credentials via actions
- Media control actions implement semantic readback to verify actual state changes (avoiding false success declarations)
- URL validation prevents malicious or unsafe destinations
- Folder access is restricted to an explicit allow-list (Downloads, Documents, Desktop, Pictures, ZARA root)

### Media Control Semantic Verification
For media actions (play/pause, next, previous), ZARA uses the PyCAW library to:
1. Capture the state before sending a media command
2. Send the Windows APPCOMMAND media control
3. Capture the state after the command
4. Compare states to verify the command had the intended effect
5. Only declare success if semantic verification confirms the state change

This prevents the "false success" issue where ZARA would claim an action worked when it only sent the command without verifying the result.

## Available PC Control Actions

### Browser Actions
- `browser_open_url` - Opens a validated URL in the default browser
- `browser_search` - Performs a Google search in the default browser

### Media Controls
- `media_play_pause` - Toggles media play/pause
- `media_next` - Skips to next media track
- `media_previous` - Returns to previous media track

### System Controls
- `os_volume` - Gets or sets system volume
- `os_brightness` - Gets or sets screen brightness
- `os_brightness_up`/`os_brightness_down` - Adjust brightness in increments
- `audio_mute`/`audio_unmute` - Mute/unmute master audio
- `audio_status` - Read real default Windows audio endpoint and active render sessions (READ_ONLY capability)

### File System Actions
- `os_open` - Opens a known safe folder from an explicit allow-list

### Application Actions
Through the `_SAFE_WINDOWS_APPS` dictionary, ZARA can safely open:
- Calculator
- Notepad
- Chrome
- Task Manager
- Settings (via ms-settings:)
- Paint
- Snipping Tool
- Microsoft Edge
- Spotify (via spotify: protocol)

## Status

**PRONTO** — Functional and tested as part of Fases 1-2. PC Control capabilities are implemented with proper gating, security hardening, and semantic verification for media controls to prevent false success declarations.