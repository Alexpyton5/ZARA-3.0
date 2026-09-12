# Gates: ZARA Lab Level 4

OWNS: core/lab_v1/**, tests/test_lab_level4.py, tests/test_front_mission_policy.py, tests/test_lab_autopilot.py, tests/test_lab_supervisor.py, frontend/src/renderer/components/zara-lab-v2/**, frontend/tests/lab-level4-contract.test.cjs

Scope: Reopen the canonical Lab mission path with cost-safe autonomous planning, execution, verification, recovery, persistence, resume, and truthful reporting.

- [x] G1: Workforce policy authorizes only explicit safe resource classes and rejects paid, unknown-cost, unavailable, and owner-disabled resources.
  CHECK: python -m pytest tests/test_lab_level4.py -q -k workforce; if ($LASTEXITCODE -eq 0) { Write-Output LAB_LEVEL4_WORKFORCE_OK }
  EXPECT: LAB_LEVEL4_WORKFORCE_OK
  EVIDENCE: 2 passed (2026-09-08)

- [x] G2: One public mission submission uses the existing MissionController and automatically plans, selects the minimum team, executes dependencies, verifies, and reports with one owner touch.
  CHECK: python -m pytest tests/test_lab_operational.py -q -k dynamic_plan_handoff; if ($LASTEXITCODE -eq 0) { Write-Output LAB_LEVEL4_GOLDEN_PATH_OK }
  EXPECT: LAB_LEVEL4_GOLDEN_PATH_OK
  EVIDENCE: dynamic plan version 2, two dependent artifacts and one automatic report passed (2026-09-08)

- [x] G3: Verification rejection triggers bounded repair and resource loss persists a waiting state without paid fallback or busy looping.
  CHECK: python -m pytest tests/test_lab_operational.py tests/test_lab_level4.py -q -k "repair or resource_wait"; if ($LASTEXITCODE -eq 0) { Write-Output LAB_LEVEL4_RECOVERY_OK }
  EXPECT: LAB_LEVEL4_RECOVERY_OK
  EVIDENCE: wrong Python rejected then repaired; resource wait persisted without extra call (2026-09-08)

- [x] G4: The canonical background supervisor resumes safe incomplete missions after restart without UI input and does not replay uncertain effects.
  CHECK: python -m pytest tests/test_lab_level4.py -q -k "background or restart or uncertain"; if ($LASTEXITCODE -eq 0) { Write-Output LAB_LEVEL4_RESUME_OK }
  EXPECT: LAB_LEVEL4_RESUME_OK
  EVIDENCE: 2 passed (2026-09-08)

- [x] G5: Existing Lab, MissionController, FrontBrain, local-command, and voice safety tests remain green.
  CHECK: python -m pytest tests/test_lab_autopilot.py tests/test_lab_mission_controller.py tests/test_lab_supervisor.py tests/test_front_mission_policy.py tests/test_front_brain.py tests/test_runtime_owner_regressions.py tests/test_voice_conversation_fluidity.py -q; if ($LASTEXITCODE -eq 0) { Write-Output LAB_LEVEL4_REGRESSION_OK }
  EXPECT: LAB_LEVEL4_REGRESSION_OK
  EVIDENCE: 307 selected Lab/FrontBrain/runtime/voice tests passed (2026-09-08)

- [x] G6: Renderer typecheck and the Lab Level 4 truthful-state contract pass.
  CHECK: npm --prefix frontend run typecheck; if ($LASTEXITCODE -eq 0) { Write-Output LAB_LEVEL4_TYPECHECK_OK }
  EXPECT: LAB_LEVEL4_TYPECHECK_OK
  EVIDENCE: npm typecheck exit 0 (2026-09-08)

- [x] G7: One final bounded real mission completes through the public production entry with exactly one owner submission and factual provider provenance.
  EVIDENCE: session_104561fe0bda COMPLETED; owner_touches=1; requested Luna then Sol; model_reported remained explicitly null; artifacts/lab-level4-real-acceptance.json (2026-09-08)

- [x] G8: Independent Terra medium review finds zero P0 and zero P1 findings in the current delta.
  EVIDENCE: Terra independent final verdict ACCEPT; P0=0; P1=0 (2026-09-08)

- [x] G9: A single successor candidate is built and verified while CURRENT zara-current-20260906-055925 remains unchanged.
  EVIDENCE: zara-current-20260908-231429 verified; packaged read-only IPC/Lab canary PASS; CURRENT remains zara-current-20260906-055925 (2026-09-08)
