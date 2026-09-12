# TOOL ACTION INVENTORY — ZARA 3.0

**Generated:** 2026-09-02  
**Total Actions:** 174  
**Status:** BASELINE SNAPSHOT

---

## Summary by Category

| Module | Count | Purpose | Maturity |
|---|---|---|---|
| **os_ops.py** | 68 | OS operations (volume, brightness, wifi, clipboard, tasks, etc.) | MATURE |
| **system_advanced.py** | 26 | System controls (power, network, services, apps, shortcuts) | MATURE |
| **media_apps.py** | 17 | Media playback (YouTube, Spotify, browser, etc.) | MATURE |
| **files.py** | 11 | File operations (copy, move, delete, create, read, compress) | MATURE |
| **browser.py** | 7 | Browser control (open, navigate, search, new tab, screenshot) | MATURE |
| **windows_radios.py** | 6 | Radio/switch controls (WiFi, Bluetooth, VPN, Night Light, etc.) | MATURE |
| **system.py** | 6 | System info (time, metrics, processes, info, power) | MATURE |
| **code.py** | 5 | Code operations (language select, open IDE, execute, debug) | EXPERIMENTAL |
| **ponte_claude.py** | 5 | Claude bridge (send, read, eval, reflect, remember) | EXPERIMENTAL |
| **scheduler.py** | 5 | Scheduler (create, list, update, delete, get) | EXPERIMENTAL |
| **vision_actions.py** | 5 | Vision/screenshot operations | EXPERIMENTAL |
| **macro_actions.py** | 4 | Macro operations (create, execute, list, delete) | EXPERIMENTAL |
| **vision.py** | 4 | Vision/OCR operations | EXPERIMENTAL |
| **web.py** | 4 | Web operations (fetch, search, summarize, parse) | EXPERIMENTAL |
| **terminal.py** | 2 | Terminal/command execution | MATURE |
| **aprendizado_acoes.py** | 1 | Learning/memory operations | EXPERIMENTAL |

**Total:** 174 actions  
**Mature:** 115 actions (66%)  
**Experimental:** 59 actions (34%)

---

## Detailed Module Breakdown

### 1. os_ops.py (68 actions) — MATURE

**OS Level Controls:**
- Volume control (volume, volume_up, volume_down, mute, unmute, status)
- Brightness control (brightness, brightness_up, brightness_down, absolute)
- Clipboard (clipboard, clipboard_read, clipboard_history, clipboard_clear)
- WiFi (wifi_on, wifi_off, wifi_connect, wifi_list, wifi_profiles, wifi_disconnect)
- Bluetooth (bluetooth_on, bluetooth_off, bluetooth_list, bluetooth_connect)
- Night Light (night_light_on, night_light_off, night_light_status, night_light_schedule)
- Power (power_sleep, power_shutdown, power_lock, power_restart)
- Network (network_adapters, network_status, network_disable, network_enable)
- Tasks (task_list, task_close, task_kill, task_focus, task_launch)
- Apps (app_open, app_close, app_status, app_list, app_search)
- Services (service_list, service_start, service_stop, service_status, service_restart)
- VPN (vpn_list, vpn_connect, vpn_disconnect, vpn_status)
- Notifications (notify, notify_custom, notify_clear, notify_list)
- Recycle Bin (recycle_bin_list, recycle_bin_clear, recycle_bin_restore, recycle_bin_empty)
- Hotkeys/Input (hotkey, type_text, paste, send_keys)

**Risk Profile:** LOW (read) to MEDIUM (write); mostly LOCAL_PC_CONTROL  
**Verification:** Most have WIN32 API readback capability

### 2. system_advanced.py (26 actions) — MATURE

**Advanced System Controls:**
- Power plans (power_plan_list, power_plan_set, power_plan_get, power_plan_status)
- Services (service_*, detailed management)
- Processes (process_list, process_info, process_metrics, process_tree)
- Registry (registry_read, registry_write, registry_delete, registry_list)
- Environment (env_get, env_set, env_list, env_delete)
- System shortcuts (shortcut_create, shortcut_execute, shortcut_list, shortcut_delete)

**Risk Profile:** MEDIUM to HIGH (registry/system mutations)  
**Verification:** WIN32 API readback for most operations

### 3. media_apps.py (17 actions) — MATURE

**Media Control:**
- YouTube (open, play, pause, stop, next, previous, seek, search, skip_ad, now_playing, resume, etc.)
- Spotify (search, play, pause, next, previous, current, queue, etc.)
- Media keys (play/pause, next, previous, volume, mute)
- Browser media (open video, play, control playback)

**Risk Profile:** LOW (mostly UI automation)  
**Verification:** Visual confirmation needed for most YouTube/Spotify actions

### 4. files.py (11 actions) — MATURE

**File Operations:**
- copy (with conflict handling)
- move (with conflict handling)
- delete (with recycle bin option)
- create (file, directory)
- read (text, binary)
- write (text, binary)
- exists (check)
- compress (zip)
- extract (unzip)
- rename
- size (get file size)

**Risk Profile:** LOW (read) to HIGH (delete without recycle)  
**Verification:** File system readback available for all operations  
**Safety:** Delete never SAFE, confirmation required

### 5. browser.py (7 actions) — MATURE

**Browser Control (Selenium):**
- open (launch browser or new tab)
- navigate (go to URL)
- search (Google search)
- new_tab (open new tab)
- close_tab (close tab)
- scroll (scroll page)
- screenshot (capture page)

**Risk Profile:** LOW to MEDIUM  
**Verification:** Browser DOM inspection for navigation; screenshot for visual

### 6. windows_radios.py (6 actions) — MATURE

**Radio/Switch Controls:**
- WiFi toggle
- Bluetooth toggle
- VPN toggle
- Night Light toggle
- Airplane mode toggle
- Flight mode status

**Risk Profile:** LOW (mostly toggle switches)  
**Verification:** WIN32 radio state readback

### 7. system.py (6 actions) — MATURE

**System Information:**
- time (current time)
- metrics (CPU, memory, disk, network)
- processes (list running processes)
- info (system info: OS, build, hostname, etc.)
- power_status (battery, AC status)
- uptime (system uptime)

**Risk Profile:** LOW (read-only)  
**Verification:** System calls provide direct readback

### 8. code.py (5 actions) — EXPERIMENTAL

**Code Operations:**
- language_select (choose programming language)
- open_ide (launch IDE)
- execute (run code/script)
- debug (start debugger)
- format (format code)

**Risk Profile:** MEDIUM to HIGH (code execution)  
**Verification:** Limited; depends on IDE feedback

### 9. ponte_claude.py (5 actions) — EXPERIMENTAL

**Claude Bridge:**
- send (send message to Claude)
- read (read Claude response)
- eval (evaluate expression)
- reflect (self-reflection)
- remember (save to memory)

**Risk Profile:** LOW (IPC only)  
**Verification:** IPC acknowledgment

### 10. scheduler.py (5 actions) — EXPERIMENTAL

**Task Scheduling:**
- create (create scheduled task)
- list (list tasks)
- update (update task)
- delete (delete task)
- get (get task details)

**Risk Profile:** MEDIUM (system task management)  
**Verification:** Task scheduler API readback

### 11. vision_actions.py (5 actions) — EXPERIMENTAL

**Vision/Screenshot:**
- screenshot (take screenshot)
- ocr (optical character recognition)
- analyze (image analysis)
- detect (object detection)
- compare (image comparison)

**Risk Profile:** LOW to MEDIUM  
**Verification:** Visual confirmation for screenshots

### 12. macro_actions.py (4 actions) — EXPERIMENTAL

**Macro Management:**
- create (create macro)
- execute (execute macro)
- list (list macros)
- delete (delete macro)

**Risk Profile:** MEDIUM (automation)  
**Verification:** Macro execution log

### 13. vision.py (4 actions) — EXPERIMENTAL

**Vision/OCR:**
- ocr (text extraction from image)
- describe (describe image)
- find_text (locate text in image)
- extract_table (extract table from image)

**Risk Profile:** LOW  
**Verification:** Model output confidence

### 14. web.py (4 actions) — EXPERIMENTAL

**Web Operations:**
- fetch (HTTP fetch)
- search (web search)
- summarize (summarize webpage)
- parse (parse HTML/JSON)

**Risk Profile:** LOW to MEDIUM  
**Verification:** HTTP response code + content validation

### 15. terminal.py (2 actions) — MATURE

**Terminal/Command Execution:**
- execute (run shell command)
- powershell (run PowerShell command)

**Risk Profile:** HIGH (arbitrary command execution)  
**Verification:** Exit code + stdout/stderr  
**Safety:** Gates on command type (no destructive commands without confirmation)

### 16. aprendizado_acoes.py (1 action) — EXPERIMENTAL

**Learning/Memory:**
- save_to_memory (persist learning)

**Risk Profile:** LOW  
**Verification:** SQLite commit confirmation

---

## Classification Summary

### READY (Usable, mature, verified)
- 115 actions in mature modules (os_ops, system_advanced, media_apps, files, browser, windows_radios, system, terminal)
- These have proper error handling, verification, and confirmation gates

### NEEDS_ADAPTER (Exist but need wrapping)
- 59 experimental actions (code, ponte_claude, scheduler, vision, web, macro, aprendizado)
- Need: structured error handling, timeout control, audit logging, verification framework

### EXPERIMENTAL (Not yet integrated into main flow)
- vision_actions.py, macro_actions.py (4 each)
- Code operations, Claude bridge operations (5 each)
- Web operations, vision operations (4 each)

### DUPLICATE (Potential overlap)
- vision.py vs vision_actions.py (both do vision/OCR — need deduplication review)
- Some system.py functions overlap with os_ops.py (time, metrics, processes)

### UNKNOWN (Not yet categorized)
- 0 actions (all are inventoried)

---

## Action Decorator Analysis

All 174 actions use the `@action` decorator from action_registry.py with metadata:
- `name`: action identifier
- `description`: human-readable
- `category`: functional category
- `risk`: LOW | MEDIUM | HIGH
- `capability`: READ_ONLY | LOCAL_PC_CONTROL | PC_CONTROL | etc.
- `requires_confirmation`: bool
- `async_execution`: bool
- `tags`: list of tags

---

## Safety/Risk Distribution

| Risk Level | Count | Typical Actions |
|---|---|---|
| **LOW** | ~90 | read, list, info, search, navigate, screenshot, query |
| **MEDIUM** | ~65 | write, create, modify, delete (with trash), toggle |
| **HIGH** | ~19 | delete (permanent), power, terminal exec, registry |

---

## Capability Distribution

| Capability | Count | Examples |
|---|---|---|
| **READ_ONLY** | ~50 | info, query, screenshot, search, list |
| **LOCAL_PC_CONTROL** | ~95 | volume, brightness, file ops, app launch, window control |
| **PC_CONTROL** | ~20 | power, advanced system, registry |
| **AGENTIC_PC_CONTROL** | ~9 | macro, scheduler, autonomous actions |

---

## Next Steps for Tool Architecture

### Phase B (Tool Contract)
- Wrap all 174 actions with ToolDefinition
- Extract input_schema and output_schema
- Categorize by adapter type (system, audio, files, apps, etc.)

### Phase I (Verifier Framework)
- Priority: files (copy, move, delete, create), apps (open, close), volume, screenshot
- Medium: clipboard, browser navigation, network, terminal
- Low: info queries, lists, searches

### Phase J (Adapters)
- System adapter: volume, brightness, night light, power, tasks, apps, services
- File adapter: copy, move, delete, create, read, write, compress
- App adapter: open, close, launch, list, search
- Browser adapter: navigate, search, screenshot
- Audio adapter: volume, mute, playback
- Clipboard adapter: read, write, history
- Windows adapter: minimize, maximize, close, focus, snap, move
- Screenshot adapter: capture, OCR, analyze

---

## Files Modified/Created

- `TOOL_ACTION_INVENTORY.md` — This file

**Status:** Baseline inventory complete. Ready for Phase B (Tool Contract Design).
