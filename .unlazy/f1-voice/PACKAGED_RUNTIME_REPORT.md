# F1 exact-candidate runtime evidence

Date: 2026-09-23. Candidate identity is bound by `.unlazy/f1-voice/candidate-identity-report.json`.

## Candidate

- BUILD_ID: `release-candidate-f1-voice-20260923-195354`
- EXE SHA-256: `67DC2A7036860A68E5312C212C31B8772AC463ED0289FCC44897867F55075E89`
- Backend SHA-256: `A96451320C554D88765F32F076A9D418133285FBB783926E2E1333A48AC9F3D6`
- ASAR SHA-256: `2F8A6521C5A9F3FDCC05CF2D1144329D22FB31D824C58709D6FA6DD7A233FAE8`
- The ASAR frontend entry extracted with `@electron/asar` matched the built `dist-frontend` bundle byte-for-byte. The extracted bundle contains `KORE_AUDIO_BUFFER` and `VOICE_TRACE`.
- Global frontend lint remains at 5 errors/62 warnings in unchanged files; the F1 `aecAudio.ts` delta passed focused ESLint. This limitation is in `FRONTEND_LINT_REPORT.md` and `BUILD_INFO.json`.

## Proven in packaged runtime

The isolated F1 candidate ran the synthetic Portuguese question “Zara, quanto é dois mais dois?” through the actual Gemini Live route. The `single_question` segment transcribed “Quanto é 2 + 2?”, returned “É quatro.”, tagged the response `gemini_live`, and emitted six Kore renderer audio chunks. The first renderer chunk arrived 5,076 ms after the last voiced synthetic input sample. Input was injected through IPC into a silent fake microphone; this does not measure a physical microphone path or room playback. It is a single observed latency, not a claimed improvement. The enclosing raw probe report has overall status `FAIL` because later long-response/interruption portions were inconclusive; this paragraph reports only the independently bounded single-question segment and does not upgrade the raw report’s status.

A separate voice-to-PC probe on the exact candidate FAILED. A locally generated spoken request for 80% was transcribed by Gemini Live as 40%; the packaged app then set Windows volume to 40%, confirmed by independent readback. The probe restored volume to 98% and confirmed mute remained off. This proves the command path can execute, but audio target accuracy failed in this run. Input used synthetic PCM over IPC and a silent fake microphone; this was not a physical microphone test. Raw report: _quarentena/organizacao-2026-09-23/voice-pc-control-f1-20260923/voice-pc-control-report.json.

On the same exact candidate, a separate PC-control probe independently read Windows state after each action: volume 98→88 (286.7 ms), mute off→on (137.1 ms), and brightness 0→5 (4,063 ms). Each was restored to its original value (98, unmuted, brightness 0). `state_restored=true`. Source report: `_quarentena/organizacao-2026-09-23/pc-controls-probes/20260923-195840-9140/REPORT.json`.

The exact F0 candidate received the same synthetic question and recognized it, but emitted no audio and returned an in-progress-turn error. Therefore there is no valid numeric before/after latency delta. F0 source report: `_quarentena/organizacao-2026-09-23/f0-baseline-20260923-201840/f0-baseline-report.json`.

An exact spoken stop phrase during an automated long response caused the packaged UI to return to LISTENING, set its playback button false, and emit no PCM chunks after the stop event. The probe had 12.1 seconds of renderer audio queued before interruption. It did not capture a transcript for “Zara, pare”; the stop event preceded the synthesized phrase’s final voiced sample by about 192 ms. This is evidence of an automated interruption event in the synthetic IPC path, not proof of lexical recognition or physical audible cutoff. Raw report: `_quarentena/organizacao-2026-09-23/f1-barge-exact-20260923-203554/barge-exact-report.json`; its raw status remains `INCONCLUSIVE_OR_FAIL` because its strict timing assertion failed.

The 118-test F1 source run also passed the focused fallback checks `test_failed_kore_initializes_fallback_once_and_plays_edge` and `test_partial_kore_audio_does_not_restart_phrase_in_fallback`. These prove the mocked fallback rules at TEST level; the package has no safe runtime failure-injection control, so this does not close the packaged fallback gate.

## Not proven / remaining gates

- No physical microphone, physical Kore listening, room continuity, or owner approval has been observed.
- No controlled early/late TTS failure test proves fallback behavior during a live response.
- No comparable numeric F0→F1 latency improvement exists because F0 produced no audio.
- NVIDIA voice catalog exploration was deferred per Alex’s instruction that Gemini Live is sufficient for now.

Evidence level: packaged automated runtime for the listed behaviors only. F1 is not fully complete; G4, G5, and owner-only G6 remain open.
