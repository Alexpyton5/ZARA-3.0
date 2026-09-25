# ZARA Lab autonomy — evidence 2026-09-25

Task: `ZARA-LAB-AUTONOMY-20260923`

## PACKAGED_RUNTIME

- Input package: `release-candidate-lab-autopilot-fallbackscope-20260925-20260925-050536`.
- Read-only packaged canary: PASS.
- Real no-queue run: `session_5ae1423b4098`.
- Owner input inserted by harness: false.
- Visible ZARA windows during run: 1.
- The Lab created the mission by itself, planned it visibly, recovered from a provider wait through an already-authorized fallback, applied a source patch in the isolated candidate, ran focused tests, obtained independent review, built a packaged candidate and completed the mission.
- Candidate tests: 16/16 PASS.
- Independent reviewer: PASS.
- Candidate build: `release-candidate-lab-source-20260925-051603`.
- Candidate packaged canary: PASS.
- Automatic promotion journal: `artifacts/releases/source-20260925-051655-271259/SOURCE_PROMOTION.json` = `COMMITTED`.
- Active build after promotion: `release-candidate-lab-source-20260925-051603`.
- Active backend SHA256: `6DC85584CF0F19548AC35DF174F7DAE4A9D73C46899837108E02DD4B152FFE7B`.
- Active source SHA256: `5e0ad5821a491ee5f12004d764c8c5d1571256d7ec1ae6eeb4f384251dfc4c0d`.
- Second read-only canary on the promoted package: PASS at `packaged-smoke-promoted-20260925/VALIDATION.json`.

## Transactional safety

Focused scenarios in `tests/test_lab_source_promotion.py`:

- healthy promotion: PASS;
- forced post-activation health failure restores known-good: PASS;
- pointer-write failure restores source/package/pointers: PASS;
- source drift blocks activation before pointer movement: PASS.

Result: 4/4 PASS.

## Evidence limits

- This proves automated packaged Lab behavior and transactional promotion/rollback.
- It is not `PHYSICAL_BY_ALEX` and does not prove the voice pipeline.
- F0/F1/F2/F4 roadmap gates remain separate from this Lab autonomy slice.
