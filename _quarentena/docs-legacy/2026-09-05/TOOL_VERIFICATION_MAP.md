# TOOL VERIFICATION MAP — ZARA 3.0

**Date:** 2026-09-02  
**Status:** BASELINE VERIFICATION FRAMEWORK  
**Purpose:** Prove that tool execution actually happened (ZARA-NAO-VERIFICADO-001)

---

## Verification Framework

Never invent success. Always have proof.

Verification states:
- **VERIFIED** — Action execution confirmed via postcondition
- **FAILED** — Action execution detected as failed
- **UNKNOWN** — Cannot determine if action executed
- **NOT_APPLICABLE** — Verification not applicable for this tool

---

## Implemented Verifiers

### 1. AlwaysVerified
**Tools:** Info queries, read-only operations  
**Logic:** Always returns VERIFIED (no mutation)  
**Confidence:** 100%

Example tools:
- system_info, system_time, system_metrics
- file_read, file_list, clipboard_read
- browser_screenshot, vision_screenshot

---

### 2. FileExistsVerifier
**Tools:** File create, file copy operations  
**Logic:** Check if file exists after operation  
**Postcondition:** Path exists + size > 0  
**Confidence:** 100% if found, 0% if not found

Example tools:
- file_create, file_copy

**Proof captured:**
- File exists: true/false
- File size in bytes
- Modification time

---

### 3. FileDeletedVerifier
**Tools:** File delete operations  
**Logic:** Check that file no longer exists  
**Postcondition:** Path does not exist  
**Confidence:** 100%

Example tools:
- file_delete (to recycle bin)

**Proof captured:**
- File exists: false

---

### 4. VolumeChangeVerifier (TODO)
**Tools:** Volume control operations  
**Logic:** Read system volume level before/after  
**Postcondition:** Volume changed to requested level  
**Confidence:** Will be 95% (±1 level tolerance)

Example tools:
- system_volume (set level)
- audio_mute, audio_unmute

---

### 5. ProcessExistsVerifier (TODO)
**Tools:** App launch operations  
**Logic:** Check if process is running  
**Postcondition:** Process found in tasklist  
**Confidence:** 90% (process may start slowly)

Example tools:
- app_open, browser_open

**Proof captured:**
- Process name
- Process ID
- Memory usage

---

### 6. WindowVisibleVerifier (TODO)
**Tools:** Window control operations  
**Logic:** Check if window appears on screen  
**Postcondition:** Window found in window list  
**Confidence:** 95%

Example tools:
- window_maximize, window_minimize, window_focus

---

### 7. ClipboardVerifier (TODO)
**Tools:** Clipboard write operations  
**Logic:** Read clipboard after write  
**Postcondition:** Clipboard contains written text  
**Confidence:** 100%

Example tools:
- clipboard_write

---

### 8. RegistryVerifier (TODO)
**Tools:** Registry write operations  
**Logic:** Read registry value after write  
**Postcondition:** Registry value set to expected value  
**Confidence:** 100%

Example tools:
- system_advanced (registry operations)

---

### 9. NetworkVerifier (TODO)
**Tools:** Network operations  
**Logic:** Check HTTP response code  
**Postcondition:** HTTP 200/301/302 received  
**Confidence:** 95%

Example tools:
- browser_navigate, web_fetch

---

### 10. BrowserNavigationVerifier (TODO)
**Tools:** Browser navigation  
**Logic:** Check page title/URL after navigation  
**Postcondition:** URL matches or page loaded  
**Confidence:** 90%

Example tools:
- browser_navigate, browser_search

---

## Verification Coverage by Category

| Category | Verifiable | Verifier | Status |
|---|---|---|---|
| **System** | 30% | Custom per tool | TODO |
| **Audio** | 20% | VolumeChangeVerifier | TODO |
| **Files** | 100% | FileExistsVerifier, FileDeletedVerifier | ✓ READY |
| **Apps** | 80% | ProcessExistsVerifier | TODO |
| **Windows** | 90% | WindowVisibleVerifier | TODO |
| **Clipboard** | 100% | ClipboardVerifier | TODO |
| **Browser** | 80% | BrowserNavigationVerifier | TODO |
| **Terminal** | 50% | Exit code + output | PARTIAL |
| **Screenshot** | 0% | Visual inspection only | NOT_APPLICABLE |
| **Vision** | 0% | Manual review only | NOT_APPLICABLE |

---

## Verification Confidence by Risk Level

| Risk | Certainty Required | Verifier Type | Examples |
|---|---|---|---|
| **SAFE** | Low (95%+) | Automatic | Read operations, lists, queries |
| **CONFIRM** | High (98%+) | File/process checks | Copy, move, app launch |
| **HIGH_RISK** | Very High (99%+) | Multi-path verification | Delete, power, registry |

---

## Verification Testing

### Unit Tests (Phase Q)
- [ ] AlwaysVerified returns VERIFIED
- [ ] FileExistsVerifier detects file creation
- [ ] FileDeletedVerifier detects file deletion
- [ ] VolumeChangeVerifier (mock) validates state change
- [ ] ProcessExistsVerifier (mock) finds process

### Integration Tests (Phase R)
- [ ] File copy → verify file exists
- [ ] File delete → verify file gone
- [ ] App launch → verify process running
- [ ] Volume change → verify system volume changed
- [ ] Clipboard write → verify clipboard contains text

---

## Verification Hooks Integration

### In ToolRouter
```python
if tool.verifier or custom_verifiers[tool_name]:
    verification = verifier(request.parameters, result_data)
    result.verification = verification
    result.verificado = verification.is_verified()
```

### In ToolResult
```python
result = ToolResult(
    success=True,
    data=...,
    verificado=False,  # Default: unverified
    verification=ToolVerificationResult(
        state="UNKNOWN",
        confidence=0.0,
    )
)
```

### In Audit Trail
```python
{
    "tool": "file_copy",
    "success": True,
    "verificado": True,  # Verified or not
    "verification_state": "VERIFIED",
    "confidence": 1.0,
}
```

---

## Custom Verifier Pattern

```python
class CustomVerifier(ToolVerifier):
    def verify(self, parameters, result_data):
        # Your verification logic here
        proof = check_postcondition(parameters)
        return ToolVerificationResult(
            state="VERIFIED" if proof else "FAILED",
            proof=proof,
            confidence=1.0 if proof else 0.0,
        )
```

---

## Status Summary

**Implemented:** 3 verifiers (AlwaysVerified, FileExistsVerifier, FileDeletedVerifier)  
**TODO (High Priority):** 3 verifiers (VolumeChangeVerifier, ProcessExistsVerifier, WindowVisibleVerifier)  
**TODO (Medium Priority):** 3 verifiers (ClipboardVerifier, RegistryVerifier, NetworkVerifier)  
**Not Applicable:** 2 verifiers (Screenshot, Vision — manual/visual)

**Coverage:** ~40% of actions have verification ready  
**Target:** 80% by end of Phase 2

---

## Files Modified/Created

- `TOOL_VERIFICATION_MAP.md` — This file
- `core/tool_verifier.py` — Verification framework + 3 implementations
- `core/tool_result.py` — ToolVerificationResult + verification state

**Next:** Implement remaining verifiers in Phase 2.
