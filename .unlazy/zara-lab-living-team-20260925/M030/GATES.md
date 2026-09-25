# Gates: M030 — memória compartilhada Obsidian

OWNS: core/obsidian_memory.py, core/lab_v1/runtime.py, core/lab_v1/autopilot.py, core/lab_v1/mission_controller.py, core/lab_v1/supervisor.py, tests/test_lab_autopilot.py, tests/test_lab_supervisor.py, frontend/src/renderer/components/zara-lab-v2/labTypes.ts, frontend/src/renderer/components/zara-lab-v2/LabRoom.tsx, frontend/src/renderer/components/zara-lab-v2/lab-room.css, .claude/CURRENT_MISSION.md, .claude/TASK_BOARD.md, .unlazy/zara-lab-living-team-20260925/GATES.md, .unlazy/zara-lab-living-team-20260925/M030/GATES.md, ZARA_ACTIVE_BUILD.json, ZARA_ACTIVE_BUILD.txt

Scope: connect real Lab model calls to vetted project notes in the configured Obsidian vault and make source/freshness visible in the packaged Lab.

- [ ] G1: the CEO and delegated agent in the room receive bounded project memory from the real vault
  EVIDENCE: the packaged session proves two real BUILDER runs consumed memory; it did not record a distinct CEO-role run, so that part remains unproven.

- [ ] G2: every Autopilot model role receives the same bounded memory mechanism, with source references recorded as events
  EVIDENCE: source path is shared by Autopilot calls and the live BUILDER calls emitted `memory.linked`; live CEO/REVIEWER/RESEARCHER role coverage remains unproven.

- [x] G3: retrieval stays under Zara-Memoria, records relative source paths only, and filters credential-like content
  EVIDENCE: source review and focused Python import/compile verified bounded paths, relative references, and credential-like filtering.

- [x] G4: the Lab UI shows vault connection, source, check time, and live-read/index status without exposing note bodies
  EVIDENCE: packaged capture `PACKAGED_RUNTIME_M030_20260925.png` shows "Obsidian conectado", `Zara-Memoria · 128 notas`, direct live-read status/check time, and relative source references in the Operations panel.

- [x] G5: one real, read-only mission in the packaged Lab confirms memory was consulted and the same run/source appears in the visible room
  EVIDENCE: canonical session `session_76fec77c5a23` completed with two `gpt-5.6-sol` runs (`run_881ae22465f7`, `run_20836694c0e7`); both persisted `memory.linked` events with relative Obsidian source paths; the report and same sources are visible in the actual packaged Lab capture. It correctly reports when the notes do not prove the requested historical claim. Earlier failed attempts remain unchanged in DB.

- [x] G6: the active EXE/ASAR/backend identity matches the build manifest and exactly one ZARA window is open
  EVIDENCE: active manifest SHA256 matched EXE, ASAR, and backend; exactly one main ZARA process matched the manifest; both backend processes belong to that same packaged process tree; app responded.

- [x] G7: the previous room build remains available for rollback and only task-owned files are committed/pushed
  EVIDENCE: M020 rollback package remains present; M030 source and checkpoint commits are pushed. No unrelated dirty files were staged.

- [x] G8: a paused mission with no live lease or started run remains visible but does not prevent a new work item in the same team room; active/queued work still blocks a second executor
  EVIDENCE: canonical session `session_76fec77c5a23` entered and completed while `session_9a31b1c26186`, `session_b0e492ae8a8e`, and `session_70369ea16bc3` remained in their previous blocked states; focused mission/supervisor regressions pass. New G9 covers the separate global-supervisor status defect exposed afterward.

- [ ] G9: old BLOCKED/BLOCKED_NEEDS_OWNER missions with no live lease or started run stay in the room history without pinning the global supervisor in BLOCKED; WAITING_RESOURCE work remains eligible for retry
  CHECK: python -m pytest tests/test_lab_supervisor.py -q
  EXPECT: 0 failed
  EVIDENCE: source fix implemented; 20/20 supervisor tests passed, including preserved blocked history and retry priority. Packaged relaunch against canonical DB remains pending.
