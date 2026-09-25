# Gates: M030 — memória compartilhada Obsidian

OWNS: core/obsidian_memory.py, core/lab_v1/runtime.py, core/lab_v1/autopilot.py, frontend/src/renderer/components/zara-lab-v2/labTypes.ts, frontend/src/renderer/components/zara-lab-v2/LabRoom.tsx, frontend/src/renderer/components/zara-lab-v2/lab-room.css, .claude/CURRENT_MISSION.md, .claude/TASK_BOARD.md, .unlazy/zara-lab-living-team-20260925/GATES.md, .unlazy/zara-lab-living-team-20260925/M030/GATES.md, ZARA_ACTIVE_BUILD.json, ZARA_ACTIVE_BUILD.txt

Scope: connect real Lab model calls to vetted project notes in the configured Obsidian vault and make source/freshness visible in the packaged Lab.

- [ ] G1: the CEO and delegated agent in the room receive bounded project memory from the real vault
  EVIDENCE: pending

- [ ] G2: every Autopilot model role receives the same bounded memory mechanism, with source references recorded as events
  EVIDENCE: pending

- [x] G3: retrieval stays under Zara-Memoria, records relative source paths only, and filters credential-like content
  EVIDENCE: source review and focused Python import/compile verified bounded paths, relative references, and credential-like filtering.

- [ ] G4: the Lab UI shows vault connection, source, check time, and live-read/index status without exposing note bodies
  EVIDENCE: pending

- [ ] G5: one real, read-only mission in the packaged Lab confirms memory was consulted and the same run/source appears in the visible room
  EVIDENCE: BLOCKED. The real launcher refused to start because the canonical Lab still has an earlier session in BLOCKED / UNCERTAIN_EFFECT, with a pending candidate-build reconciliation. No new mission was created and the earlier session was preserved.

- [x] G6: the active EXE/ASAR/backend identity matches the build manifest and exactly one ZARA window is open
  EVIDENCE: active manifest SHA256 matched EXE, ASAR, and backend; exactly one main ZARA process matched the manifest; both backend processes belong to that same packaged process tree; app responded.

- [x] G7: the previous room build remains available for rollback and only task-owned files are committed/pushed
  EVIDENCE: M020 rollback package remains present; M030 source and checkpoint commits are pushed. No unrelated dirty files were staged.
