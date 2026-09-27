# Gates — ZARA-VOICE-REPAIR-AND-OMNIVOICE-20260927

## Acceptance

- [ ] V1 — `sounddevice` imports in the ZARA `.venv`; rebuilt sidecar packages the native module and starts `voice-status` cleanly.
- [ ] V2 — OmniVoice installs only in `%LOCALAPPDATA%\ZARA3\runtimes\omnivoice`; weights remain local, no key/service/cost, and NC model weights are not distributed.
- [ ] V3 — the UI selects Kore or OmniVoice; Kore remains default and saved preference contains no credentials.
- [ ] V4 — a Kore failure/timeout falls back to local OmniVoice; no retry after partial Kore audio and user interruption never triggers fallback replay.
- [ ] V5 — missing or failed OmniVoice degrades safely to the existing configured local/free voices.
- [ ] V6 — voice-focused Python tests, full Python suite, frontend tests, typecheck, and Electron build pass before publication.
- [ ] V7 — exact packaged candidate is identified by source revision, build ID/time, EXE hash, sidecar hash and automated smoke.
- [ ] V8 — Alex verifies the exact candidate physically: mic starts and the selected/fallback voice speaks; no microphone permission is changed by automation.
- [ ] V9 — push and <=10-line report in `ZOE-INBOX\concluidas`; do not close the mission while any earlier gate is red or unproven.

## Current evidence

- `sounddevice` import and sidecar packaging smoke: `RUNTIME_AUTOMATED` passed at the prior checkpoint.
- OmniVoice install, selector, fallback, full suite, and physical microphone: pending.
- Current branch baseline: `wip/ciclo7-20260927`, HEAD `bfb676fb4d47863ab7d16be4baa4dd6c14d6379f`.
