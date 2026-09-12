# Gates: immutable complete candidate builder
OWNS: tools/build_source_candidate.py, tests/test_build_source_candidate.py
Scope: reject incomplete builds; never reidentify or recopy source underneath old binaries; clean canary env.
- [ ] G1: Builder regression tests exercise rejection and complete receipt success
  CHECK: .venv\Scripts\python.exe -m pytest tests/test_build_source_candidate.py -q
  EXPECT: passed
  EVIDENCE: pending
- [ ] G2: Independent root review confirms no failed-build promotion or rewritten identity
  EVIDENCE: pending
