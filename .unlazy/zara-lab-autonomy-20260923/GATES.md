# Gates: Zara Lab autonomous improvement

OWNS: core/lab_v1/service.py, core/lab_v1/supervisor.py, core/lab_v1/evolution.py, core/lab_v1/autopilot.py, core/lab_v1/runtime.py, core/lab_v1/fleet.py, core/lab_v1/workforce_policy.py, core/lab_v1/providers/nvidia.py, core/lab_v1/candidate_source.py, core/lab_v1/source_mission.py, core/lab_v1/release.py, core/lab_v1/telegram_gate.py, tools/build_candidate.py, tools/build_source_candidate.py, core/ipc_handlers.py, frontend/src/preload.ts, frontend/src/renderer/types/global.d.ts, frontend/src/renderer/components/zara-home/ZaraHome.tsx, frontend/src/renderer/components/zara-lab-v2/useLabRoom.ts, frontend/src/renderer/components/zara-lab-v2/LabRoom.tsx, tests/test_lab_autonomous_startup.py, tests/test_lab_evolution.py, tests/test_lab_improvement_scheduler.py, tests/test_lab_candidate_source.py, tests/test_lab_source_mission.py, tests/test_lab_feedback_pipeline.py, tests/test_lab_autopilot.py, tests/test_lab_runtime.py, tests/test_lab_fleet_certification.py, tests/test_lab_workforce_policy.py, tests/test_lab_release.py, .claude/CURRENT_MISSION.md, .claude/TASK_BOARD.md, .unlazy/zara-lab-autonomy-20260923/**

Scope: with autonomy enabled, the packaged app starts one no-queue Lab mission; agents visibly discuss and plan in their shared group, then create and verify source in one bounded candidate. Alex explicitly authorized automatic promotion of low-risk Lab-only changes after all tests, independent review, packaged canary, and rollback checks pass. No medium/high/unknown-risk or out-of-scope change may auto-promote. Use one candidate at a time and isolate both backend and Electron data under the task profile.

- [x] G1: persisted autonomy starts exactly one background supervisor and scheduler on app startup
  CHECK: python -m pytest tests/test_lab_autonomous_startup.py -q
  EXPECT: 4 passed
  EVIDENCE: TEST — 4 passed (2026-09-23). Covered first-run opt-in, saved pause across service restart, coupled toggle, idempotent startup, and supervisor/scheduler lock exclusion.

- [ ] G2: exact packaged app starts one mission with an empty feedback queue; agent discussion and plan appear in the shared ZARA Core group without an owner prompt
  EVIDENCE: PACKAGED_RUNTIME — app started the queued feedback mission without a post-launch UI prompt, but mission ended FAILED (INTERNAL_REVIEW_FAILED:REPAIR_LIMIT_AFTER_REPLAN); no accepted candidate diff/build. Full details: FINAL_OBSERVATION.json.

- [ ] G3: generated work stays in the single candidate; owner source and database are unchanged; focused tests and independent reviewer receipt are persisted
  EVIDENCE: PACKAGED_RUNTIME — production source hashes match the pre-run protection baseline and no promotion occurred; focused candidate pytest passed 2/2 for the generated regression file, but independent review rejected semantic/test coverage, so no verified candidate or reviewer PASS. Full details: FINAL_OBSERVATION.json.

- [x] G4: pause, daily budget, quota wait, and restart-resume stop duplicate or unbounded work
  CHECK: 9 focused regression tests across `test_lab_improvement_scheduler.py`, `test_lab_supervisor.py`, `test_lab_autopilot.py`, and `test_lab_background_absence.py`
  EXPECT: 9 passed
  EVIDENCE: TEST — 9 passed (2026-09-23): owner toggle; real mission planning; shared daily cap; supervisor pause; delegated/reviewed execution; SQLite schedule restart; bounded quota failover; mission checkpoint resume; no rerun after completion. This is isolated test runtime evidence, not provider or packaged execution proof.

- [x] G6: source missions execute existing relevant ZARA tests as read-only sandbox inputs
  CHECK: "C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\.venv\Scripts\python.exe" -m pytest tests/test_lab_candidate_source.py tests/test_lab_source_mission.py tests/test_lab_feedback_pipeline.py tests/test_lab_autonomous_startup.py -q
  EXPECT: 36 passed, 1 skipped
  EVIDENCE: TEST — 36 passed, 1 skipped in 63.38s. Covers candidate sandbox read-only test execution, source-mission wiring, feedback pipeline, and autonomous startup; one existing platform-dependent test was skipped.

- [x] G5: official candidate identity and active build record match the exact opened executable
  EVIDENCE: PACKAGED_RUNTIME — BUILD_INFO and ZARA_ACTIVE_BUILD identify release-candidate-lab-autonomy-live-20260923-220225; recorded EXE SHA256 matches the actual opened executable (67DC2A7036860A68E5312C212C31B8772AC463ED0289FCC44897867F55075E89). UI capture: real-packaged-run-20260923-2232/app-final.png.

- [x] G7: the frozen-runtime improvement probe returns a bounded inconclusive result instead of timing out the scheduler
  CHECK: focused regression in tests/test_lab_evolution.py and tests/test_lab_improvement_scheduler.py
  EXPECT: scheduler reaches a dispatch or a bounded NO_WORK/DEDUP/BUDGET state; never FAILED because the PyInstaller EXE was called with Python CLI flags
  EVIDENCE: TEST — included in the 38 focused Lab tests passed on 2026-09-23. PACKAGED_RUNTIME — the exact candidate's first isolated cycle recorded bounded `NO_WORK` (0 sources found at the then-unresolved packaged workspace); no Python CLI timeout occurred.

- [ ] G8: one current candidate only; all real-runtime proof uses a disposable profile passed to both Electron and backend via ZARA3_HOME; owner data remains read-only
  EVIDENCE: PACKAGED_RUNTIME — pending isolated live run

- [ ] G9: packaged supervisor resolves the project checkout and tolerates the first-run database without mission_controls
  CHECK: focused `test_lab_supervisor.py` regressions plus one packaged empty-queue run
  EXPECT: workspace points to the checkout containing `ZARA_ACTIVE_BUILD.json`; first supervisor tick reports an idle/monitoring state rather than `SUPERVISOR_NEEDS_RECONCILIATION`
  EVIDENCE: TEST — 38 focused Lab tests passed, including packaged checkout discovery and no-mission-table first tick. PACKAGED_RUNTIME — pending.

- [ ] G10: first owner objective provisions ZARA Core through policy-authorized actual model proof, using the authenticated user-configured provider/model fallback when the default Claude CLI cannot infer
  CHECK: focused tests in `test_lab_runtime.py`, `test_lab_fleet_certification.py`, `test_lab_autopilot.py`, and `test_lab_workforce_policy.py`
  EXPECT: team bootstrap is idempotent; failed, unapproved, or unavailable models never gain `model.text`; owner-declared free Kimi K3 and GLM 5.3 require exact allowlist entries and real inference proof; successful proof registers the existing role profile and is reused after restart without another model call.
  PACKAGED_RUNTIME: initial live attempt reported `WAITING_RESOURCE` because the disposable profile intentionally had no NVIDIA API key and both Claude CLI calls returned `AUTH_REQUIRED`. The canonical ZARA config has an NVIDIA key and a cached model catalog; neither secret was copied into the disposable profile. New candidate must inject only the selected key through the process environment, never write it to evidence, and certify the selected models with real provider calls.

- [ ] G11: the opened packaged app accepts one real Lab task and the proven agents visibly work on it
  EVIDENCE: pending UI + isolated SQLite/source-candidate observation. Must show actual agent messages, persisted plan, nonempty isolated candidate diff, focused verification and independent reviewer PASS, low-risk packaged canary, automatic promotion journal, active candidate health PASS, and no second ZARA window. A dispatch/acknowledgement alone does not pass.
