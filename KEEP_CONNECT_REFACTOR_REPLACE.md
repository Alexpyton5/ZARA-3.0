# CLASSIFICATION: KEEP / CONNECT / REFACTOR / REPLACE

## KEEP (Mature, No Changes Needed)

```
✅ core/ipc_handlers.py
   - Mature IPC dispatcher
   - Well-documented, stable
   - Handles 34+ channels
   - Status: production-ready

✅ core/gemini_live_voice.py
   - Voice streaming works
   - Barge-in implemented
   - Gate logic clear
   - Status: production, single-provider risk noted

✅ core/intent_classifier.py
   - Regex → intent mapping
   - LLM fallback
   - Local-deterministic actions list
   - Status: good for MVP, limited NLU

✅ core/action_registry.py
   - Action dispatch clean
   - Safety gates ok
   - Confirmation prompts work
   - Status: production

✅ core/actions/system.py
   - Windows system control
   - Volume, brightness, night light
   - Tested regularly
   - Status: production

✅ core/actions/browser.py
   - Selenium browser control
   - Chrome automation
   - Search, navigation, screenshots
   - Status: production

✅ core/actions/files.py
   - File operations (create, copy, delete)
   - Confirmation for deletes
   - Path validation
   - Status: production

✅ core/actions/terminal.py
   - Command execution
   - Output capture
   - Sandboxed
   - Status: production

✅ core/actions/media_apps.py
   - YouTube, Spotify desktop
   - Tested
   - Status: production

✅ core/conversation_history.py
   - SQLite persistence
   - Turn logging
   - Metadata capture
   - Status: production

✅ core/action_confirmation.py
   - Permission prompts
   - User consent capture
   - Status: production

✅ core/audit_log.py
   - Audit trail
   - Compliance ready
   - Status: production

✅ frontend/src/main.ts
   - Electron main process
   - Spawn, lifecycle, signals
   - IPC setup
   - Status: production

✅ frontend/src/preload.ts
   - Context isolation enforced
   - API minimized
   - Safe bridge
   - Status: production

✅ frontend/public/zara-titanium-emerald/
   - Current UI build output
   - Glassmorphism design
   - Voice visualization
   - Status: elected, baseline

✅ CLAUDE.md
   - Governance documented
   - Rules of operation clear
   - Status: reference

✅ .claude/rules/
   - Time zone rules (9-person team)
   - Evidence taxonomy
   - Build/release rules
   - Status: reference

✅ pyproject.toml
   - Dependencies pinned
   - Version control good
   - Status: production

✅ config/api_keys.json (pattern)
   - Secrets separated
   - Not in git
   - Status: production
```

---

## CONNECT (Exists, Needs Wiring)

```
🔗 core/aprendizado.py
   Current: Captures intent patterns, generates embeddings
   Problem: Not integrated to decision-making
   Action: Wire embeddings to memory retrieval during planning
   Priority: Medium
   Effort: Refactor planning layer

🔗 core/local_rag.py
   Current: Local retrieval-augmented generation
   Problem: Never called
   Action: Integrate to context retrieval stage
   Priority: Low
   Effort: Medium

🔗 core/macro_engine.py
   Current: Macro execution engine exists
   Problem: Not exposed in UI, not triggered
   Action: Add macro UI control, wire to dispatcher
   Priority: Medium (roadmap feature)
   Effort: High

🔗 core/cronometro.py
   Current: Scheduler framework
   Problem: No event loop integration
   Action: Hook into asyncio loop, test with cron patterns
   Priority: Medium
   Effort: High

🔗 core/mcp/servers/*
   Current: MCP server skeletons
   Problem: No central orchestrator
   Action: Build MCP registry, coordinate tool access
   Priority: Low (future)
   Effort: Very High

🔗 core/model_router.py
   Current: Partial model selection logic
   Problem: Single Gemini provider in voice, no switching
   Action: Implement fallback routing (Gemini → Claude → local)
   Priority: High (de-risk voice)
   Effort: High

🔗 Memory system (core/memory/, OBSIDIAN integration)
   Current: Schema defined, not in code
   Problem: Obsidian vault not wired
   Action: Implement Obsidian read/write, integrate to planning
   Priority: High (core feature)
   Effort: Very High
```

---

## REFACTOR (Works, Needs Organization)

```
🔧 core/autonomy_engine.py
   Problem: Reimplements intent logic already in intent_classifier.py
   Action: Consolidate into single intent path, keep autonomy as planning layer
   Reason: Avoid dual intent routing (source of bugs)
   Effort: High
   Risk: Regression if autonomy has logic classifier lacks

🔧 frontend/package.json
   Problem: npm vs pnpm conflict, duplicate lock files
   Action: Choose ONE manager, delete redundant locks
   Reason: Dependency hell, unpredictable installs
   Effort: Low
   Risk: Low if done carefully with test build

🔧 core/voice_stt.py + core/voice_tts.py
   Problem: TTS cascade (Kore→Edge→SAPI) is ad-hoc
   Action: Centralize VoicePipeline orchestrator
   Reason: Single source of voice I/O truth
   Effort: Medium
   Risk: Regression in voice output

🔧 Action safety gates
   Problem: Confirmation is manual regex per action
   Action: Implement risk matrix (file delete = high risk, get time = low risk)
   Reason: Scale permissions to hundreds of actions
   Effort: High
   Risk: Low if tested

🔧 requirements.txt vs pyproject.toml
   Problem: Possible duplication, unclear which is source
   Action: Keep pyproject.toml as source, remove requirements.txt (use uv)
   Reason: Single dependency source of truth
   Effort: Low
   Risk: Medium if workflows depend on requirements.txt

🔧 core/paths.py + config handling
   Problem: Path resolution scattered
   Action: Centralize in ConfigManager
   Reason: Single point for user data locations
   Effort: Low
   Risk: Low

🔧 Logging
   Problem: Print-based logging, no structured logs
   Action: Use Python logging module, JSON output
   Reason: Observability, debugging easier
   Effort: High
   Risk: Medium (risk of breaking error messages)

🔧 frontend/tests/
   Problem: Coverage low (~10%), mostly unit tests
   Action: Add integration tests (voice→action→verify)
   Reason: E2E confidence
   Effort: Very High
   Risk: Low (only adds tests)

🔧 Build process
   Problem: No BUILD_INFO.json manifest on candidates
   Action: Add manifest before packaging (BUILD_ID, SHA256, timestamp, commit)
   Reason: Traceability (know what EXE contains what code)
   Effort: Low
   Risk: Low
```

---

## REPLACE (Architecture Inadequate)

```
❌ 4x UI Versions → Keep Titanium Emerald ONLY
   Current: zara-titanium-emerald (built)
            zara-interface (Next.js draft)
            zara-interface-codigo-completo (duplicate)
            zara-app (Tauri prototype)
   Problem: 4 interfaces compete, confuse build, waste disk
   Action:
      1. Confirm Titanium Emerald is elected
      2. Move others to _quarentena/ui-legacy/
      3. Delete from release builds
   Effort: Low
   Risk: Low if Titanium is really the chosen one
   Blocker: None, but need Alex's confirmation

❌ Manual intent regex → NLU engine
   Current: intent_classifier.py regex + fallback LLM
   Problem: Cannot handle complex requests ("find contract and send email")
   Action: Implement real NLU (intent + entity + context)
   When: Phase 2 (after stabilization)
   Reason: Multi-step planning needs rich intent representation
   Effort: Very High
   Risk: High (may break existing regex paths)

❌ Single Gemini provider → Model Router
   Current: Only Gemini Live for voice
   Problem: API breaks or becomes expensive → ZARA is silent
   Action: Implement Model Router with fallbacks
      ├─ Gemini Live (premium, preferred)
      ├─ Claude API (fallback, paid)
      ├─ Local model (e.g., Ollama, free)
      └─ Restart in degraded mode if all fail
   When: Phase 1 (high priority)
   Effort: High
   Risk: Medium (voice is critical)

❌ Independent action execution → Planner
   Current: Each action standalone, no multi-step
   Problem: Cannot handle "find file, open it, extract data, send email"
   Action: Build Planner (decompose goal → subgoals → actions)
   When: Phase 2
   Effort: Very High
   Risk: High (changes core dispatcher)

❌ Manual safety gates → Risk matrix
   Current: Confirmation by regex (delete action = always ask)
   Problem: Doesn't scale to 100+ actions with nuanced risk
   Action: Risk Matrix (Severity × Impact × User Context)
   When: Phase 1 (medium priority)
   Effort: High
   Risk: Low (permission refactoring)

❌ Conversation history only → Real memory system
   Current: SQLite conversation log, not integrated to decisions
   Problem: ZARA doesn't "remember" or use past context during planning
   Action: Integrate memory retrieval to context building
      ├─ Obsidian Vault (second brain)
      ├─ Vector index (embeddings)
      ├─ Structured DB (structured facts)
      └─ Memory graph (relationships)
   When: Phase 2
   Effort: Very High
   Risk: High (changes how ZARA reasons)
```

---

## DEPRECATED (Delete After Inventory)

```
🗑️ core/claude_brain.py
   Lines: 50
   Content: Empty stub
   Reason: Never implemented
   Action: Delete
   Blocker: None

🗑️ frontend/release-candidate-* (7 old folders)
   Size: ~7.7 GB total
   Content: Old Electron builds
   Reason: No manifest, can't trace, consuming disk
   Action: Archive to _quarentena/release-candidates-legacy/
   Blocker: None (but verify no active deployment uses them)

🗑️ zara-interface/ + zara-interface-codigo-completo/
   Size: ~500 MB
   Content: Old UI drafts
   Reason: Titanium Emerald is elected
   Action: Move to _quarentena/ui-legacy/
   Blocker: Confirm Titanium is final

🗑️ zara-app/ (Tauri prototype)
   Size: ~5 GB
   Content: Rust + web build, incomplete
   Reason: Decision to stay with Electron
   Action: Archive to _quarentena/prototypes/tauri/
   Blocker: None

🗑️ wiki/ (old documentation)
   Content: Abandoned docs
   Reason: Not used, out of date
   Action: Archive to _quarentena/docs-legacy/
   Blocker: None

🗑️ skills/ (empty or templates)
   Content: Skill system scaffolding
   Reason: Never populated
   Action: Keep scaffolding, archive templates to _quarentena/skill-templates/
   Blocker: None
```

---

## UNKNOWN (Investigate Before Touch)

```
❓ core/proactive_monitor.py
   Lines: 250
   Status: Unclear, marked experimental
   Action: Audit callers, decide keep/delete

❓ core/vision_actions.py
   Lines: 300
   Status: Never wired to UI
   Action: Audit use cases, connect or deprecate

❓ tools/* (boilerplate_gen, media_downloader, etc)
   Lines: ~2000 total
   Status: Utility scripts, unclear if used
   Action: Audit for active use, deprecate unused

❓ core/mcp/* (MCP server implementations)
   Lines: ~1000 total
   Status: Experimental, no orchestrator
   Action: Roadmap for Phase 2, not blocking Phase 1

❓ profiles/ directory
   Status: Old data, no reader evident
   Action: Backup to _quarentena/, investigate format
```

---

## Summary by Phase

### Phase 0: Audit & Stabilization (Now)
- ✅ Read all code
- ✅ Identify KEEP/CONNECT/REFACTOR/REPLACE/DEPRECATED
- ✅ Generate architecture documents
- ⏳ Get Alex approval on this plan

### Phase 1: Safety & De-risk (Weeks 1-4)
- 🔨 Fix build manifest (BUILD_INFO.json)
- 🔨 Consolidate UI (keep Titanium, archive others)
- 🔨 Unify package manager (npm or pnpm, not both)
- 🔨 Model Router (de-risk voice provider lock-in)
- 🔨 Risk matrix for permissions
- 🔨 Clean _quarentena/ (move deprecated files)
- ✅ Result: ZARA is traceable, less fragile, safer

### Phase 2: Memory & Planning (Weeks 5-12)
- 🔨 Obsidian integration
- 🔨 Real NLU engine
- 🔨 Planner (multi-step reasoning)
- 🔨 Connect learning to decisions
- ✅ Result: ZARA can handle complex requests

### Phase 3: Polish & Expand (Weeks 13+)
- 🔨 Multi-platform (macOS, Linux)
- 🔨 Macro system
- 🔨 Automation workflows
- 🔨 Performance optimization
- ✅ Result: ZARA 3.0 production-ready

---

## End of Classification
