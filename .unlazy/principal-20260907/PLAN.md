# Principal architect checkpoint

Scope: principal-20260907
Depth: tree 2
Mode: orchestrated
Contract revision: 2

## Contract

TASK_ID: PRINCIPAL-20260907
GOAL: Find and implement the shortest demonstrable improvement in bounded ZARA autonomy, using existing systems; continue through verification and a reviewable checkpoint.
SCOPE: Current Lab mission/workforce and runtime evidence; select one coherent implementation slice after independent discovery. The attached briefing explicitly permits postponing speculative capabilities.
FILES_ALLOWED: This scope and artifacts/principal-20260907/** for discovery. Exact production files will be named before implementation.
FILES_FORBIDDEN: Credentials, user memory/data, historical evidence, existing packages and unrelated dirty files.
BASELINE: HEAD 7e3624c44cdbce5a4f1114229884cc7deb41d346 plus existing extensive dirty state. Active manifest points to 20260906-055925; provenance must be audited before runtime claims.
EXPECTED_DELTA: A tested, bounded autonomous behavior, chosen from current gaps rather than a new parallel architecture.
TESTS: Focused isolated tests for the selected behavior and affected existing contracts; command oracles added before edits.
PACKAGED_TEST: Isolated candidate only if feasible; report exact level reached.
PHYSICAL_TEST: Only Alex can attest; do not promote automation to physical evidence.
ROLLBACK: Back up every preexisting source file before editing; keep baseline packages and data intact.
STOP_CONDITION: High risk or cost requires owner authority; quota low means atomic checkpoint and exact resume. No speculative API spending.

Interfaces: Existing Lab store/controller/adapters remain canonical; agents return bounded Markdown findings with paths and evidence levels.
Host launch mode: Codex native subagents. Maximum two discovery leaves concurrently; root reviews policies and requests independently.
Toolchain: Windows PowerShell, local .venv Python, installed Node; no upgrades.
Manual review: Root verifies judgments and existing evidence; independent final hostile reviewer checks changed behavior and claims.

## Current contract inventory

| ID | Required outcome or constraint | Owner | Observing gate or manual review | Disposition | Revision |
|---|---|---|---|---|---|
| C1 | Identify actual next autonomy bottleneck and canonical integration | leaf-1 | leaf-1:G1, root review | ACTIVE | 1 |
| C2 | Preserve historical runtime proof and rollback identity | leaf-2 | leaf-2:G1, root review | ACTIVE | 1 |
| C3 | Implement and verify one coherent measurable improvement | root | GATES:I1 (specific contract added before code) | ACTIVE | 1 |
| C4 | Luna front default, manual premium selection, no silent paid fallback, Claude disabled | root | GATES:P1, relevant regression tests | ACTIVE | 1 |
| C5 | Bounded resources, truthful runs/actions/verification, no unrestricted execution | root | GATES:P1, adversarial review | ACTIVE | 1 |
| C6 | Evaluate provider hypotheses factually without paid calls or large downloads | root | GATES:P2, source-backed decision | ACTIVE | 1 |
| C7 | Reuse memory, voice, task and history; stage cognitive/cinematic proposals by dependency | root | GATES:P2 | ACTIVE | 1 |
| C8 | First decision covers bottleneck, rejected assumptions, architecture, implementation, proof, postponed work, new capability and next step | root | GATES:R1 | ACTIVE | 1 |
| C9 | Exact resume, changed files, tests, provider calls, known broken and nonrepetition instructions | root | GATES:R1 | ACTIVE | 1 |

## Tree

root: autonomous product checkpoint
- leaf-1: existing autonomy architecture and smallest missing behavior
- leaf-2: packaged evidence and safe candidate path
- root integration: implement chosen behavior, test and independently review

## Dispatch

| Leaf | Owns | Needs | Tier | Planned wave | State |
|---|---|---|---|---|---|
| leaf-1 | artifacts/principal-20260907/architecture.md | none | judgment | discovery | READY |
| leaf-2 | artifacts/principal-20260907/build-evidence.md | none | judgment | discovery | READY |
| leaf-3 | frontend/src/renderer/components/zara-home/TextCommandInput.tsx, frontend/src/renderer/components/zara-home/BrainSelector.tsx, frontend/src/renderer/components/zara-home/brain-selector.css | none | judgment | frontend | READY |
| leaf-4 | artifacts/principal-20260907/review.md | none | judgment | review | READY |

## Selected implementation contract (revision 2, before code)

Root owns core/lab_v1/front_brain.py, core/lab_v1/service.py, core/ipc_handlers.py, core/lab_v1/providers/codex_app_server.py, tests/test_front_brain.py, tests/test_front_brain_ipc.py, tests/test_lab_codex_app_server.py, tests/test_front_mission_policy.py and checkpoint scripts/artifacts. Existing files are backed up before edits. Leaf-3 exclusively owns the three frontend files in the dispatch table.

Acceptance: front conversation defaults to Luna, premium changes only through explicit engine-change/config-set selection, existing conversation/Session survives selection and restart, text and voice use the same real Lab invocation, no legacy API fallback; unavailable/quota failure is truthful and leaves selected model unchanged. One call per front turn, no automatic delegation; failed/interrupted front turns are not replayed. Lab mission submit/autopilot/autonomy-enable fails closed pending explicit bounded workforce policy rather than silently picking Astra. Existing completed Golden artifacts remain intact. Codex conversation requires live account type ChatGPT and pins official provider; API-key account denied before thread/turn. UI uses existing engine.list/change/config.get/message.send with factual availability and visible Send icon, no fake waveform.

UI interface: engine.list -> {current, engines:[{id,name,status}], health}; engine.change -> {success,engine} or error; config.get current_engine reflects persisted selection; message.send keeps existing shape, server rejects a payload model differing from selected. No new renderer IPC channels.

This checkpoint does not yet implement general workforce budgeting, autonomous learning, voice acoustics, self-promotion, or cinematic redesign. They remain next-stage product work explicitly permitted to be sequenced by the briefing.

## Discovery discrepancy

AGENTS.md boot paths .Codex/ORG.md, WORKING_MODEL.md, CURRENT_MISSION.md, TASK_BOARD.md and DECISIONS.md do not exist. .codex contains agents and config only. .ceo state is September 3 and stale relative to September 7 artifacts. Preserve discrepancy rather than recreate invented history.

## Owner routing rule — 2026-09-07

Optimize cost and effectiveness: use Luna for light work, Terra or Sol for intermediate work, and Astra only for genuinely difficult work. Notify Alex before any model change or reasoning-effort increase. Current setting remains Sol at medium effort.
