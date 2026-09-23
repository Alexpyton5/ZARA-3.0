# F2/F3 source map — read-only preparation

Date: 2026-09-23. This records source observations only; no new F2/F3 implementation or packaged runtime proof is claimed.

## F2 — model catalog and selector

- Conversation selector entry: `frontend/src/renderer/components/zara-home/BrainSelector.tsx` → `engine-list` / `engine-change` in preload → `FrontBrain.snapshot()` / `select()` in `core/lab_v1/front_brain.py`, routed through `core/ipc_handlers.py`.
- The text router catalog in `core/model_router.py` is separate from Lab provider discovery (`core/lab_v1/providers/nvidia.py`, `opencode.py`, `runtime.py`, and `LabRoom.tsx`). There is no single tested catalog shared by the chat selector and Lab participant picker.
- OpenCode models are sourced from CLI/cache, filtered by availability, then capped at eight. `kimi-k3` exists as a provider alias but can be omitted from the selector because the selector uses discovered catalog rows, not the alias map. Whether it is accessible on Alex’s current account/build was not tested here.
- Gemini Live is modeled as a voice transport and excluded from the text-brain list by source design. It should be exposed as a voice mode, not presented as a text brain. Runtime availability in the packaged build was not re-tested during this map.
- Proposed proof after implementation: in one identity-bound package select Kimi K3, send a short prompt, verify requested provider/model and reported provider/model in the turn receipt, then verify selection persistence. Check Gemini Live as a voice mode separately.

## F3 — Lab autonomy and code promotion

- `core/ipc_handlers.py` snapshot handler initializes `LabV1Service` when the Lab is opened; service startup can start `AutonomySupervisor`. Background supervision is enabled by default, but the distinct evolution scheduler is disabled by default. This source observation does not prove bots spontaneously talk to each other on app launch.
- Missions, messages, runs, events, and controls persist in SQLite through `core/lab_v1/store.py`. Existing UI (`frontend/src/renderer/components/zara-lab-v2/LabRoom.tsx` and `useLabRoom.ts`) shows plans, execution, and deliveries; it does not provide a classic Kanban board.
- `Autopilot` begins from a submitted objective. The source contains isolated code-change/sandbox, tests, candidate release, independent review, canary, and owner approval gates for production promotion. Packaged runtime operation of these gates is not proven, and the Lab screen does not expose the full approval flow.
- Quota retry/backoff and mission persistence exist in source. A unit test verifies SQLite survives a new store instance; this is not a packaged Lab test. No test proving bots converse, plan, code, validate, or promote in the packaged app was found in this read-only pass.
- Before autonomous coding can be called working, the vertical runtime proof must observe: at least two bots exchanging messages, a proposed plan, a code patch in an isolated workspace, tests run against that patch, reviewer approval/rejection, and no production promotion without the owner gate.

## Worktree hygiene note

- In this worktree, `voice/` and `memory/` are source code and remain present. A separate prior audit found a `voice/` folder under quarantine in the canonical Downloads checkout; that checkout was not modified in this task.
- The current quarantine manifest covers 1,024 files / 92,680,738 bytes. The 8.5 GB cleanup target and the claimed 35 dead stubs/memories remain unproven here.
