# Gates: real internal ZARA autonomy

Scope: Close planner prewritten solutions and catalog pseudo-work; prove one real existing issue repaired in isolated ZARA candidate source by persisted internal model Runs. CURRENT/rollback and Hermes source stay untouched.

- [ ] G1: Planner output cannot supply complete solutions; reports claim only actual Runs; mocked adapters cannot certify production proof.
  CHECK: .venv\Scripts\python.exe -m pytest tests/test_lab_real_work_contract.py -q
  EXPECT: passed
- [ ] G2: Candidate source changes, actual test execution, path confinement, before/after failure evidence work.
  CHECK: .venv\Scripts\python.exe -m pytest tests/test_lab_candidate_source.py -q
  EXPECT: passed
- [ ] G3: Canonical public entry, controller, planner, builder, independent reviewer, persisted handoffs, actual source/test outputs and autonomous report complete a real mission with one initial input.
  EVIDENCE: pending real production-path mission; mocks forbidden for this gate.
- [ ] G4: Regression and typecheck pass; package/candidate identity and CURRENT preservation have factual receipts.
  EVIDENCE: pending delta checks.
- [ ] G5: Hermes calls/agents/integration are zero and no external Hermes source is modified.
  EVIDENCE: pending source/runtime receipts.
