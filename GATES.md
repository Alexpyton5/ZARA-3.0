# ZARA Recovery Gates

- [ ] G1: Provider-blocked stale mission no longer deadlocks new owner message
  CHECK: .venv\Scripts\python.exe -m pytest tests/test_lab_autopilot.py tests/test_lab_mission_controller.py -q
  EXPECT: 60 passed
  EVIDENCE: passed in focused canonical environment

- [ ] G2: Active or uncertain mission still blocks supersession
  CHECK: .venv\Scripts\python.exe -m pytest tests/test_lab_autopilot.py tests/test_lab_mission_controller.py -q
  EXPECT: 60 passed
  EVIDENCE: passed in focused canonical environment

- [ ] G3: Voice responds to one real wake-word turn on the exact packaged candidate
  MANUAL: owner must perform physical test
  EVIDENCE: pending owner physical test
