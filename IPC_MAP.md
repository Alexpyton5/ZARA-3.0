# IPC Map — ZARA 3.0

**Date:** 2026-09-02  
**Milestone:** M5

---

## Overview

IPC (Inter-Process Communication) between Electron main process and Python sidecar via stdin/stdout.

**Architecture:**
```
Renderer (React)
    ↓ ipcRenderer.invoke/send
Electron Main (main.ts)
    ↓ sendToPython() / stdin
Python Sidecar (ipc_handlers.py)
    ↓ stdout
Electron Main
    ↓ ipcMain.handle resolve/reject
Renderer (React)
```

**Current IPC channels:** 28 main channels + event handlers

---

## Channel Inventory (Alphabetical)

| # | Channel | Direction | Type | Producer | Consumer | Purpose |
|---|---|---|---|---|---|---|
| 1 | `action-execute` | Renderer→Python | Async | Renderer | Backend | Execute action with confirmation |
| 2 | `action-list` | Renderer→Python | Async | Renderer | Backend | List available actions |
| 3 | `config-get` | Renderer→Python | Async | Renderer | Backend | Get config value |
| 4 | `config-set` | Renderer→Python | Async | Renderer | Backend | Set config value |
| 5 | `conversation-history-clear` | Renderer→Python | Async | Renderer | Backend | Clear conversation history |
| 6 | `conversation-history-list` | Renderer→Python | Async | Renderer | Backend | List conversation turns |
| 7 | `engine-change` | Renderer→Python | Async | Renderer | Backend | Switch voice engine (Gemini/Claude/local) |
| 8 | `engine-list` | Renderer→Python | Async | Renderer | Backend | List available engines |
| 9 | `interrupt` | Renderer→Python | Async | Renderer | Backend | Interrupt/barge-in (stop TTS) |
| 10 | `lab-proposal-create` | Renderer→Python | Async | Renderer | Backend | Create lab proposal (experimental feature) |
| 11 | `lab-proposal-decide` | Renderer→Python | Async | Renderer | Backend | Decide on lab proposal |
| 12 | `lab-send` | Renderer→Python | Async | Renderer | Backend | Send lab message |
| 13 | `lab-state` | Renderer→Python | Async | Renderer | Backend | Get lab state |
| 14 | `memory-galaxy-list` | Renderer→Python | Async | Renderer | Backend | List memory galaxy (learning data) |
| 15 | `reminder-cancel` | Renderer→Python | Async | Renderer | Backend | Cancel scheduled reminder |
| 16 | `reminder-create` | Renderer→Python | Async | Renderer | Backend | Create reminder |
| 17 | `reminder-list` | Renderer→Python | Async | Renderer | Backend | List reminders |
| 18 | `send-message` | Renderer→Python | Async | Renderer | Backend | Send text message (user input) |
| 19 | `supercerebro-status` | Renderer→Python | Async | Renderer | Backend | Get supercérebro status (on/off) |
| 20 | `supercerebro-toggle` | Renderer→Python | Async | Renderer | Backend | Toggle supercérebro (gates complex reasoning) |
| 21 | `system-info` | Renderer→Python | Async | Renderer | Backend | Get system info (CPU, memory, disk) |
| 22 | `system-metrics` | Renderer→Python | Async | Renderer | Backend | Get current system metrics |
| 23 | `voice-mute` | Renderer→Python | Async | Renderer | Backend | Mute/unmute voice input |
| 24 | `voice-start` | Renderer→Python | Async | Renderer | Backend | Start voice recognition |
| 25 | `voice-status` | Renderer→Python | Async | Renderer | Backend | Get voice status |
| 26 | `voice-stop` | Renderer→Python | Async | Renderer | Backend | Stop voice recognition |
| 27 | `window-close` | Main→None | Sync | Main | System | Close app window |
| 28 | `window-maximize` | Main→None | Sync | Main | System | Maximize app window |
| 29 | `window-minimize` | Main→None | Sync | Main | System | Minimize app window |

---

## Event Handlers (Async Updates from Python)

| Event | Direction | Producer | Consumer | Purpose |
|---|---|---|---|---|
| `response` | Python→Renderer | Backend | Renderer | Response to user query |
| `voice-level` | Python→Renderer | Backend (stream) | Renderer (VoiceParticleSphere) | Real-time voice level (0-1) |
| `typing` | Python→Renderer | Backend | Renderer | Backend is processing/thinking |
| `confirmation-request` | Python→Renderer | Backend | Renderer | Permission prompt for risky action |
| `error` | Python→Renderer | Backend | Renderer | Error from backend |
| `status-update` | Python→Renderer | Backend | Renderer | Status change (voice on/off, etc) |

---

## Message Format

### Renderer → Python (stdin)

```json
{
  "type": "send-message|voice|action-execute|...",
  "payload": {
    "text": "...",
    "action": "...",
    "params": {}
  },
  "requestId": "uuid"
}
```

### Python → Renderer (stdout)

```json
{
  "type": "response|voice-level|confirmation-request",
  "requestId": "uuid",
  "payload": {
    "text": "...",
    "success": true|false,
    "output": "...",
    "error": "...",
    "level": 0.0-1.0
  }
}
```

---

## Security Baseline (M5)

**Electron Security:**

- ✓ `contextIsolation: true` (enabled)
- ✓ `nodeIntegration: false` (disabled)
- ✓ `preload.ts` exposes minimal API
- ✓ `enableRemoteModule: false` (secure)

**IPC Validation:**

- ✓ All channels use `ipcMain.handle()` (not `on()` for risky operations)
- ✓ Renderer can invoke → Main can reject
- ✓ No direct stdin/stdout access from renderer

**Known Issues:**

- None currently; baseline secure

---

## Future Channels (Planned, not yet implemented)

- `model-change` — Switch between Gemini/Claude/local
- `obsidian-sync` — Sync with Obsidian vault
- `planner-decompose` — Multi-step planning request
- `skill-create` / `skill-execute` — User-defined automations

---

## Current Usage Patterns

**Most frequently used:**
1. `send-message` (text input)
2. `voice-start` / `voice-stop` (voice control)
3. `interrupt` (barge-in)
4. `action-execute` (PC control)

**Experimental:**
- `lab-*` channels (raciocinio livre experiments)
- `supercerebro-*` (gate for complex reasoning)

**Infrastructure:**
- `voice-level` stream (constant updates during voice capture)
- `confirmation-request` (blocks action until user decides)

---

## Status

| Criterion | Status |
|---|---|
| All channels documented | ✓ |
| Security baseline verified | ✓ |
| No deprecated channels found | ✓ |
| Context isolation enforced | ✓ |
| Preload bridge secure | ✓ |

**Baseline Established:** IPC is traceable, secure, and ready for Phase 2

