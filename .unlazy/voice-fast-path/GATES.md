# Gates: ZARA voice fast path

OWNS: core/gemini_live_voice.py, core/ipc_handlers.py, tests/test_voice_conversation_fluidity.py, tests/test_voice_latency_markers.py

- [x] G1: Voice dispatches the selected FrontBrain before the discarded Gemini draft completes
  CHECK: .venv\Scripts\python.exe -m pytest tests/test_voice_conversation_fluidity.py -q
  EXPECT: passed

- [x] G2: One voice-turn record contains the six requested latency markers and deltas
  CHECK: .venv\Scripts\python.exe -m pytest tests/test_voice_latency_markers.py tests/test_cronometro.py -q
  EXPECT: passed

- [x] G3: Voice, barge-in, FrontBrain and local command regressions remain green
  CHECK: .venv\Scripts\python.exe -m pytest tests/test_front_brain_ipc.py tests/test_voice_pipeline_safety.py tests/test_voice_tts_cascade.py tests/test_unified_zara_channel_capability.py -q
  EXPECT: passed

- [x] G4: Renderer typecheck passes
  CHECK: npm --prefix frontend run typecheck
  EXPECT: exited zero

- [ ] G5: Physical before/after latency uses three owner samples on the same phrase
  EVIDENCE: pending owner physical test on the next single candidate
