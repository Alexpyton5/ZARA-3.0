# Intent Baseline — ZARA 3.0

**Date:** 2026-09-02  
**Milestone:** M6

---

## Overview

Intent resolution pipeline for ZARA voice/text input.

**Current flow:**
```
User voice/text
    ↓ STT (voice) / direct text
Normalized text
    ↓ (1) Try deterministic regex (LOCAL_DETERMINISTIC_ACTIONS)
    ↓ (2) Try LLM fallback (intent_classifier.py)
    ↓ (3) If both fail, respond "não entendi"
Action name
    ↓ ActionRegistry dispatch
Execute action
```

---

## Module Inventory

### core/pc_voice_intent.py (Deterministic Intent Routing)

**Type:** Regex-based pattern matching  
**Status:** PRIMARY (hot path)  
**Lines:** ~350

**Core function:** `_resolve_pc_intent(text: str) → str | None`

**Built-in patterns (Examples):**

| Text Pattern | Action | Output |
|---|---|---|
| "zara, que horas são?" | `current-time` | "São 14:30" |
| "diminua o volume" | `volume-down` | "Volume reduzido" |
| "aumente o brilho" | `brightness-up` | "Brilho aumentado" |
| "abra o youtube" | `open-youtube` | "Abrindo YouTube..." |
| "copie" | `clipboard-copy` | "Copiado" |
| "minimize" | `minimize-window` | "Minimizado" |

**LOCAL_DETERMINISTIC_ACTIONS set:**
```python
# Actions that NEVER need supercérebro gate
LOCAL_DETERMINISTIC_ACTIONS = {
    "current-time",
    "volume-up", "volume-down", "volume-get",
    "brightness-up", "brightness-down", "brightness-get",
    "night-light-on", "night-light-off",
    "open-chrome", "open-youtube", "open-calculator",
    "sleep",
    "minimize-window", "maximize-window", "close-window",
    "screenshot",
    "clipboard-copy", "clipboard-paste", "clipboard-get",
    ...
}
```

**Gating:** Actions NOT in this set require `supercérebro_allowed = True`

### core/intent_classifier.py (LLM Fallback)

**Type:** Model-based intent resolution  
**Status:** SECONDARY (cold path, after regex fails)  
**Lines:** ~350

**Core function:** `classify(text: str, allowed_actions: List[str]) → IntentGuess | None`

**Logic:**

1. Build action catalog from ActionRegistry
2. Call LLM with prompt: "Given text and action list, classify intent"
3. Parse JSON response: `{"action": "...", "confidence": 0.0-1.0}`
4. Validate action exists in ActionRegistry
5. Return `IntentGuess(action, confidence)` or `None`

**Models (priority order):**
- `nvidia_nemotron_super` (free, ~6-16s)
- `nvidia_glm52` (fallback)
- `nvidia_nemotron_ultra` (slower)

**Constraints:**
- Max output: 800 tokens
- Min confidence: 0.6
- Timeout: 20s (slow but recovers correctly)
- Only runs if regex fails

**Status:** Isolated, not wired to main path (intentional, Phase 2 task)

### core/autonomy_engine.py (Raciocinio Livre Experiments)

**Type:** Alternative intent routing  
**Status:** EXPERIMENTAL (parallel implementation, not used)  
**Lines:** ~700

**Issue:** DUPLICATES intent_classifier logic

**Status flags:**
- `autonomy_enabled` (default: False)
- Feature-gated behind experimental toggle

**Purpose:** Test alternative reasoning before integrating into main path

**Plan:** M6 will map; M7 will test; unify in Phase 2 refactor

---

## Current Action Registry

**Total registered actions:** 20+

**Categories:**

| Category | Examples | Status |
|---|---|---|
| **System** | volume, brightness, night-light, sleep, screenshot | ✓ WORKING |
| **Browser** | open-chrome, open-youtube, search | ✓ WORKING |
| **File ops** | create-file, delete-file, copy-file | ✓ WORKING |
| **Clipboard** | copy, paste, get | ✓ WORKING |
| **Window** | minimize, maximize, close | ✓ WORKING |
| **Info** | current-time, battery, cpu-usage | ✓ WORKING |
| **Future** | (model-router, planner, obsidian, skills) | ⧖ TODO |

---

## Test Behaviors (M6 Baseline)

**Goal:** Establish test coverage for current intent routing before Phase 2 refactor

### Test 1: Deterministic Intent (Regex)

```python
def test_deterministic_volume_down():
    result = resolve_pc_intent("diminua o volume")
    assert result == "volume-down"
```

**Current status:** Regex patterns exist; behavior tested manually

### Test 2: Local Action Gating

```python
def test_local_action_no_gate():
    # volume-down is in LOCAL_DETERMINISTIC_ACTIONS
    assert not needs_superbrain_gate("volume-down")

def test_action_needs_gate():
    # hypothetical_complex_action is not local
    assert needs_superbrain_gate("hypothetical_complex_action")
```

### Test 3: LLM Fallback (Isolated)

```python
def test_intent_classifier_valid_action():
    classifier = IntentClassifier(allowed_actions=["volume-up", "open-youtube"])
    result = classify("turn it up")
    assert result.action in ["volume-up"]  # or None
```

### Test 4: Confidence Filtering

```python
def test_low_confidence_rejected():
    # If model confidence < 0.6, reject
    result = classify("xyzzy qwerty abcd")  # gibberish
    assert result is None or result.confidence >= 0.6
```

---

## Workflow (Current)

```
[VOICE INPUT]
    ↓
[STT or TEXT]
    ↓
[NORMALIZE: lowercase, accent-strip]
    ↓
[PC_VOICE_INTENT regex]
    ├─ MATCH? → Dispatch action
    └─ NO MATCH?
        ↓
    [INTENT_CLASSIFIER LLM fallback]
        ├─ CLASSIFY? → Dispatch action
        └─ NO CLASSIFY?
            ↓
        [RESPOND: "Não entendi ainda"]
```

---

## Known Issues

1. **Duplication:** `intent_classifier.py` + `autonomy_engine.py` both do intent routing
   - **Impact:** Code confusion, harder to test
   - **Plan:** Unify in Phase 2 refactor

2. **No behavioral tests:** Regression suite for voice commands is minimal
   - **Impact:** Hard to validate improvements
   - **Plan:** Add M7 smoke tests

3. **LLM fallback latency:** 6-20s in cloud, blocks response
   - **Impact:** Slow for unexpected commands
   - **Mitigation:** Only runs after regex fails (hot path unaffected)

4. **No context in classification:** Each intent resolved in isolation
   - **Impact:** Can't do "open file from last search"
   - **Plan:** Add context in Phase 2 (Planner)

---

## Compatibility

**Voice vs Text:** Both use same pipeline (verified in ipc_handlers.py)

**Voice flow:** STT → normalize → intent_classifier → dispatch  
**Text flow:** direct input → normalize → intent_classifier → dispatch

**Assertion:** If it works by voice, it should work by text

---

## Next Steps (Post-M7)

1. **M7:** Add behavioral smoke tests (essential commands)
2. **Phase 2:** Integrate intent_classifier into main path (behind flag)
3. **Phase 2:** Unify autonomy_engine with intent_classifier
4. **Phase 2:** Add context awareness (multi-turn intent)
5. **Phase 3:** Implement Planner (decompose complex intents)

---

## Baseline Status

| Item | Status |
|---|---|
| Deterministic routing documented | ✓ |
| LLM fallback documented | ✓ |
| Action registry mapped | ✓ |
| Local gating rules clear | ✓ |
| Voice/text parity verified | ✓ |
| Test strategy defined | ✓ |

**Baseline established:** Intent resolution is traceable and ready for Phase 2 consolidation

