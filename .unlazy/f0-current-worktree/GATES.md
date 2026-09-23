# Gates: F0 current-worktree reconciliation

OWNS: tools/build_candidate.py, .unlazy/f0-current-worktree/**, ZARA_ACTIVE_BUILD.json, ZARA_ACTIVE_BUILD.txt

Scope: preserve the F0 evidence, produce an identity-bound candidate without deleting earlier candidates, and prove one safe packaged PC-control path.

- [x] G1: artifacts removed from the checkout during the fast-forward have been recovered into quarantine with file hashes and a manifest
  EVIDENCE: _quarentena/organizacao-2026-09-23/recovered-fast-forward-20260923-184256/MANIFEST.json; six recovered files listed and SHA-256 values recorded

- [ ] P0.1: quarantine inventory completed without deleting or reclassifying preserved material
  STATUS: PARTIAL — 819 existing quarantine files (57,749,157 bytes) inventoried with SHA-256 in _quarentena/MANIFEST_P0.1_20260923.json; no bytes freed. The aggregate "35 stubs/dead memories" is still not enumerated. Its members and live references are unproven, so they remain protected and unmoved.
  CHECK: `python .unlazy/f0-current-worktree/verify_quarantine_manifest.py`
  EXPECT: `QUARANTINE_MANIFEST_PASS files=819 bytes=57749157`

- [x] G2: the official builder accepts a named external base and retains prior phase candidates
  EVIDENCE: .unlazy/f0-current-worktree/build-sentinel-report.json; `F0_BUILD_SENTINEL_PASS`; sentinel preserved under `_quarentena/`

- [x] G3: the new candidate's identity file matches its EXE, backend, ASAR, and build ID
  EVIDENCE: .unlazy/f0-current-worktree/candidate-identity-report.json; `CANDIDATE_IDENTITY_PASS`; focused `TestBuildIdentity` 2/2 passed

- [x] G4: the isolated packaged app accepts reversible controls and Windows readback confirms every postcondition; original state is restored
  EVIDENCE: `_quarentena/organizacao-2026-09-23/pc-controls-probes/20260923-190841-2868/REPORT.json`; volume, mute and brightness passed; final state equals initial state; `PC_CONTROL_PROBE_PASS`

Owner-only voice approval belongs to F1 and is intentionally outside F0. It cannot be satisfied by automation.
