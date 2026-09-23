# Gates: F1 Voice

All evidence must be bound to the `BUILD_ID`, EXE SHA-256, backend SHA-256, and ASAR SHA-256 of one candidate.

- [x] G1 SOURCE: the change set is limited to F1 voice modules/tests and the official builder's full-frontend option; `core/model_router.py` and Lab-only hunks are absent.
- [x] G2 TEST: 118 focused tests passed; 22 were skipped from the known >50s voice-window module. Python syntax and the candidate builder's Ruff check passed.
- [ ] G3 PACKAGED_RUNTIME: exact candidate answers a direct conversation once and completes a PC command with an independent Windows postcondition; original state restored.
- [ ] G4 PACKAGED_RUNTIME: long streamed response, explicit interruption, and controlled early/late TTS failure show ordered audio and no voice switch after audio begins.
- [ ] G5 MEASUREMENT: before/after use the same stimulus and report recognized-text→first renderer audio, VAD-inferred timing separately, plus full PC action timings.
- [ ] G6 VOICE_PHYSICAL: Alex hears and approves Kore quality/continuity on the exact candidate. Owner-only.
- [ ] G7 P1.8: exploratory NVIDIA voice result and limitations recorded.

F1 cannot be reported fully complete while G6 is unchecked. F2 follows only after the physical gate is resolved.

Frontend lint note: full lint reports 5 existing errors/62 warnings in unchanged files; the sole F1 frontend delta (`aecAudio.ts`) passes focused ESLint. See `FRONTEND_LINT_REPORT.md`; the candidate identity will retain this limitation rather than label global lint as passed.
