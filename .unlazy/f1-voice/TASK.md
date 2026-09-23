# TASK — ZARA-F1-VOICE-20260923

TASK_ID: ZARA-F1-VOICE-20260923
GOAL: Restore direct Kore conversation, remove duplicate/discarded conversational output, keep voice output stable, repair capture/buffering, and measure the packaged candidate with evidence tied to its exact identity.
SCOPE: P1.1–P1.8 only. No F2 model catalog changes and no F3 Lab changes. `core/ipc_handlers.py` remains Chief-only.
FILES_ALLOWED: `core/ipc_handlers.py` (F1 hunks only); `core/gemini_live_voice.py`; `core/voice_stt.py`; `core/voice_tts.py`; `frontend/src/renderer/lib/aecAudio.ts`; focused existing F1 voice tests; `.unlazy/f1-voice/**`; `tools/build_candidate.py` only to make the official builder include the changed frontend and freshly rebuilt backend; active build identity only through that tool.
FILES_FORBIDDEN: `core/model_router.py` catalog additions; Lab service/dispatch changes; canonical checkout; unrelated tests or UI.
BASELINE: F0 checkpoint `30d463a` on `codex/zara-master-20260923`. Preserve its quarantined artifacts and the external baseline candidate.
ACCEPTANCE:
- P1.1: an authorized natural conversation is answered by Gemini Live/Kore directly, persisted/displayed once, without calling the selected front brain for a duplicate.
- P1.2: a direct conversational turn produces no generated-and-discarded executor draft and no duplicate spoken answer. Executor actions must continue to suppress unverified Live drafts; if the Live transport still generates a draft while classifying an action, report that residual explicitly.
- P1.3: a second Live/Kore synthesis trip is permitted only for `LOCAL_FREE`/`FREE_PROVEN`; unknown/paid routes do not use that extra trip.
- P1.4: Kore chunks remain ordered across AudioContext resume, stale queues are invalidated, and explicit interruption stops current sources.
- P1.5: fallback may start only before any Kore audio is delivered; Alex interruption never restarts the response in another voice.
- P1.6: trace points distinguish inferred VAD timing, first returned audio, renderer delivery, and PC action timing; no proxy is labeled physical latency.
- P1.7: physical voice approval is Alex-only and remains pending until he hears the exact candidate.
- P1.8: record any NVIDIA voice catalog probe as exploratory; do not imply model/catalog integration.
TESTS: focused voice route, capture, TTS cascade, buffering, and interruption regressions only.
PACKAGED_TEST: exact candidate identity, one direct natural conversation, one reversible PC command, long audio/chunk playback, controlled interruption/fallback where the harness can induce it, OS postcondition for PC action, and state restoration.
PHYSICAL_TEST: owner listens to the exact identified candidate; automation cannot satisfy VOICE_PHYSICAL.
ROLLBACK: preserve each candidate and trace in `_quarentena/` with a manifest; revert only the F1 commit if evidence shows regression.
STOP_CONDITION: never substitute code inspection or synthetic audio for owner approval; do not proceed to F2 until F1's required physical gate is explicitly resolved.
