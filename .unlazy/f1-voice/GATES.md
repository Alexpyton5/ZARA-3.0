# Gates: F1 Voice

All evidence must be bound to the `BUILD_ID`, EXE SHA-256, backend SHA-256, and ASAR SHA-256 of one candidate.

- [x] G1 SOURCE: the change set is limited to F1 voice modules/tests and the official builder's full-frontend option; `core/model_router.py` and Lab-only hunks are absent.
- [x] G2 TEST: 118 focused tests passed; 22 were skipped from the known >50s voice-window module. Python syntax and the candidate builder's Ruff check passed.
- [x] G3 PACKAGED_RUNTIME: exact candidate completed one direct Gemini Live conversation and volume/mute/brightness controls with independent Windows postconditions; original state restored. See `PACKAGED_RUNTIME_REPORT.md`.
- [ ] G4 PACKAGED_RUNTIME: automated exact-phrase interruption produced a stop event and no later PCM chunks. Fallback regressions passed at TEST level (`test_failed_kore_initializes_fallback_once_and_plays_edge`, `test_partial_kore_audio_does_not_restart_phrase_in_fallback`), but controlled TTS failure has not been exercised inside the packaged app. No physical playback claim.
- [ ] G5 MEASUREMENT: F1 synthetic IPC stimulus produced first renderer audio 5,076 ms after the last voiced sample. F0 heard the same stimulus but produced no audio, so a numeric before/after latency delta is unavailable. Physical microphone latency remains unmeasured.
- [ ] G6 VOICE_PHYSICAL: Alex hears and approves Kore quality/continuity on the exact candidate. Owner-only.
- [x] G7 DEFERRED BY OWNER: Alex said Gemini Live is sufficient for now; do not spend time on NVIDIA voice exploration in this mission pass.

F1 cannot be reported fully complete while G4–G6 are unchecked. F2 follows only after the physical gate is resolved.

Frontend lint note: full lint reports 5 existing errors/62 warnings in unchanged files; the sole F1 frontend delta (`aecAudio.ts`) passes focused ESLint. See `FRONTEND_LINT_REPORT.md`; the candidate identity will retain this limitation rather than label global lint as passed.
