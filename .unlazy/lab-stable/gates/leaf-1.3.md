# Gates: natural source scope
OWNS: core/lab_v1/source_scope.py, core/lab_v1/candidate_source.py, tests/test_lab_source_scope.py, tests/test_lab_candidate_source.py
Scope: select existing safe source from natural product requests and support bounded frontend/config text edits.
- [ ] G1: Scope and candidate boundary tests pass, unsafe paths reject
  CHECK: .venv\Scripts\python.exe -m pytest tests/test_lab_source_scope.py tests/test_lab_candidate_source.py -q
  EXPECT: passed
  EVIDENCE: pending
- [ ] G2: Root checks source routing integration and actual candidate diffs
  EVIDENCE: pending
