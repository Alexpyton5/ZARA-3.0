# Capability Registry in ZARA 3.0

## Overview

The capability registry is a system that allows ZARA to load actions on demand, keeping only essential actions exposed at startup. This improves startup time and reduces memory usage by lazily loading capabilities only when needed.

## How It Works

At startup, ZARA exposes only a small set of fundamental actions (23 actions) defined in `FUNDAMENTAL_ACTIONS`. When an action is requested that is not currently loaded, the capability registry:

1. Locates the module that implements the action (via `_ACTION_TO_MODULE` mapping)
2. Imports the module only if needed
3. Registers the requested action while keeping sibling actions from the same module hidden
4. Returns success if the action was loaded and registered

This prevents importing one action from exposing all actions in its module, which would defeat the purpose of lazy loading.

## Fundamental Actions

The following actions are always loaded at startup:

- system_time
- system_info
- system_metrics
- audio_status
- audio_mute
- audio_unmute
- media_play_pause
- media_next
- media_previous
- os_volume
- os_brightness
- os_brightness_up
- os_brightness_down
- os_clipboard_read
- os_clipboard
- window_minimize
- window_maximize
- window_restore
- web_search
- web_fetch
- files_list
- files_read
- files_search

## Configuration

The capability registry requires no special configuration. It is enabled by default and works automatically.

## Usage

Actions are loaded automatically when requested through the agent's interface. For example, when a user asks for a command that requires a specific capability, the registry loads it behind the scenes.

## Implementation Details

The capability registry is implemented in `core/capability_registry.py` and uses:

- `_ACTION_TO_MODULE`: maps action names to their implementing modules
- `_DEFERRED_ACTIONS`: caches actions whose modules have been imported but not yet registered
- Thread-safe locking to prevent race conditions during module loading

## Testing

The capability registry is covered by tests in:
- `test_capability_registry.py`
- `test_capability_registry_final.py`
- Various other test files that use lazy loading

## Status

**PRONTO** — Functional and tested as part of Fases 1-2. Only 23 fundamental actions are exposed at startup; other actions are loaded on demand.