# F1 focused test evidence

Run: 2026-09-23, worktree `codex/zara-master-20260923`, before the F1 candidate build.

- `.zara-tests/latest.json` did not exist in this worktree, so there was no reusable recent result.
- The worktree has no `.venv`; tests used the explicit ZARA Python at `C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\.venv\Scripts\python.exe` from the current worktree directory.
- `ALLOW_LIVE_TESTS` was removed and `ZARA_TEST_MODE=1` was set.
- Scope: 7 targeted voice files (`test_voice_conversation_fluidity`, `test_voice_pipeline_safety`, `test_voice_tts_cascade`, `test_voice_usability`, `test_gemini_live_voice_responsiveness`, `test_voice_latency_markers`, `test_voice_barge_in`).
- Result: **118 passed, 22 skipped, 43.15 s**.
- All 22 skips came from the existing module-level skip in `test_gemini_live_voice_responsiveness.py`: it opens a voice-engine window and has a known >50-second hang. No `-m voice` opt-in was used.
- This is TEST evidence only. It does not prove that the packaged app hears Alex or that Kore sounds continuous in the room.
- `py_compile` passed for all changed Python modules/tests. `ruff check tools/build_candidate.py` passed. A broader Ruff comparison against F0 found **0 new findings**; the same 11 existing findings remain in `core/ipc_handlers.py` and 10 in `core/gemini_live_voice.py`.
