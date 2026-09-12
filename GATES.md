# Gates: ZARA low-cost workforce and release readiness

OWNS: core/model_router.py, tests/test_cost_safe_brain_policy.py, tests/test_lab_fleet_certification.py, tests/test_lab_router.py, tests/test_lab_quota_recovery.py, artifacts/golden-path/LOW-COST-CERTIFICATION-20260907.md

Scope: Prove the cost-safe brain policy honestly and leave package readiness explicitly measurable.

- [x] G1: Cost-safe routing accepts only factual local/free models
  CHECK: .venv\\Scripts\\python.exe -m pytest tests/test_cost_safe_brain_policy.py tests/test_lab_router.py tests/test_lab_quota_recovery.py tests/test_router_integrity.py -q
  EXPECT: passed
  EVIDENCE: automatic-evidence=v1; definition-sha256=13b29ced8e1f792441a260beaca2e96bb276bb3f50b58de822f022a567f182e5; exit=0; EXPECT=matched; output-sha256=fa430a12d8f0631f6cc4630eeee98b42d60ec48a57a99f81b08b8bf4941d2a5f; output-bytes=824; shell=C:\Windows\system32\cmd.exe; cwd=C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002; path=b37572340b07/37 entries

- [x] G2: Fleet certification and low-cost policy agree on worker availability
  CHECK: .venv\\Scripts\\python.exe -m pytest tests/test_lab_fleet_certification.py -q
  EXPECT: passed
  EVIDENCE: automatic-evidence=v1; definition-sha256=63b4ca21bbff6234de01d5e1ea84038d8e876954fd6764330798bb304ce5ec4b; exit=0; EXPECT=matched; output-sha256=27544663ef7f696e9b4ec668675e575235845554990ab1be35f42303f71ae7c8; output-bytes=580; shell=C:\Windows\system32\cmd.exe; cwd=C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002; path=b37572340b07/37 entries

- [x] G3: Package candidate is not claimed before real Electron validation
  EVIDENCE: pending manual review of current build pointer, staging directories, and packaged canary report

- [x] G4: Current result and next command are recorded in the autonomy handoff
  CHECK: .venv\\Scripts\\python.exe -c "from pathlib import Path; p=Path('artifacts/autonomy-one-shot/RESUME.md'); t=p.read_text(encoding='utf-8'); assert 'NEXT' in t and len(t)>500; print('HANDOFF_OK')"
  EXPECT: HANDOFF_OK
  EVIDENCE: automatic-evidence=v1; definition-sha256=5253ab651f2523226af21aa19034692d54c41d69844d6cc433ee56aabc5f096b; exit=0; EXPECT=matched; output-sha256=bd0d3135d59285a3a5c7309e511a8be08b03ee8fbcc321756a7c94ba2bee4d3a; output-bytes=12; shell=C:\Windows\system32\cmd.exe; cwd=C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002; path=b37572340b07/37 entries
