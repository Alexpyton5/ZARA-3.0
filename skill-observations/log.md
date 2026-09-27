# Skill observations

## Open observations

### OBS-20260921-001 — Physical failure must reopen the earliest product gate
- **Status:** open
- **Task:** ZARA physical recovery and packaging
- **Observation:** Automated source tests and packaged canaries repeatedly passed while owner-visible voice and Lab interaction still failed or behaved incorrectly. The workflow needs an explicit rule that a physical counterexample reopens the earliest causal gate and blocks packaging claims until the exact behavior is reproduced in an isolated runtime.
- **Evidence:** Owner reported no spoken response and a nonresponsive Lab after candidate launch; later traces showed approximately 20 seconds to first audio and the Lab treated a greeting as an engineering mission.
- **Suggested action:** Update the relevant ZARA validation skill after the current product repair is complete.

### Observation 1: Runtime binding is part of configuration completeness

**Status:** OPEN
**Date:** 2026-09-21
**Session context:** Completing an interrupted agent-profile feature in a desktop multi-agent application.
**Skill:** managing-zara
**Type:** open-source
**Phase/Area:** Acceptance evidence

**Issue:** A partially implemented feature persisted editable agent identity, model, and permissions but did not route that data through the actual agent turn or source-work permission checks. The UI could therefore claim customization while runtime behavior remained unchanged.

**Suggested improvement:** Add an explicit acceptance gate for configurable behavior: prove persistence, next-turn prompt binding, effective model routing, permission enforcement, version history, and rollback before declaring the feature complete.

**Principle:** Configuration is not implemented until the next real execution consumes it and a test proves the resulting behavior changed.

### Observation 2: Overnight autonomy needs bounded resumable work

**Status:** OPEN
**Date:** 2026-09-22
**Session context:** Owner requested overnight, continuous improvement of a desktop agent and its internal automation Lab.
**Skill:** autopilot-execution
**Type:** internal
**Phase/Area:** Autonomous execution guardrails

**Issue:** The available autonomy skill describes continuous implementation and packaging, but does not define how an overnight request is translated into safe, resumable units when the working tree is already dirty and production promotion is gated.

**Suggested improvement:** Add a required nightly mode: create a named task contract, run one causal/reversible unit per heartbeat, retain the previous build, test before the next unit, and publish only a new candidate after integration gates pass.

**Principle:** Continuous work is reliable only when every restart can identify the current unit, its guardrails, evidence and rollback without trusting conversation memory.

### Observation 3: Verify the build tool’s actual payload boundary before promotion

**Status:** OPEN
**Date:** 2026-09-23
**Session context:** ZARA F1.1 direct Gemini Live response build.
**Skill:** managing-zara / validating-packaged-runtime
**Type:** workflow
**Phase/Area:** Build and evidence

**Issue:** The official candidate tool successfully ran but performs a sidecar-only swap over an old Electron base, so it cannot include a changed Python dispatcher unless the base ASAR already contains the source change. The output looked fully identified while omitting the requested runtime delta.

**Suggested improvement:** Before building, map exactly which changed source files each build pipeline packages, then inspect the relevant embedded artifact/hash or source identity before calling it a candidate for owner testing.

**Principle:** A successful build command proves packaging mechanics, not that the requested change entered the package.

### Observation 4: Preserve prior build outputs in the official builder

**Status:** OPEN
**Date:** 2026-09-23
**Session context:** Full frontend and voice-backend packaging for ZARA F1.
**Skill:** managing-zara / validating-packaged-runtime
**Type:** workflow
**Phase/Area:** Build safety and rollback

**Issue:** The official build script's help and project policy said it created a new output without changing existing candidates, but its post-build cleanup recursively deleted every older `release-candidate-*` directory. That would erase rollback evidence during a phase-isolated build.

**Suggested improvement:** Keep prior build directories immutable; make cleanup a separate quarantined maintenance task. Add a full-packaging mode to the official tool when the source delta crosses frontend and backend boundaries.

**Principle:** A build pipeline must preserve the exact prior artifacts needed to identify and roll back a regression.
### Observation 5: Local test labels must distinguish packaged runtime

**Status:** OPEN
**Date:** 2026-09-25
**Session context:** Observed ZARA Lab agent mission correcting workflow-role template selection while owner watched the live app.
**Skill:** task-observer
**Type:** internal
**Phase/Area:** Runtime evidence communication

**Issue:** The visible conversation described an upcoming local deterministic pytest run as a real test, while the task card correctly said local sandbox tests. The baseline and candidate both passed 11 cases, so the verifier rejected the result because it did not prove a before-fail/after-pass correction. This made the evidence level confusing to the owner.

**Suggested improvement:** In Lab messages and task cards, label local checks as “teste local no sandbox”; reserve “teste no app empacotado” for actual execution in the packaged app. Generate status wording from the recorded evidence type.

**Principle:** Evidence labels must say where the software actually ran.

### Observation 6: Build wrappers need an environment escape hatch

**Status:** OPEN
**Date:** 2026-09-26
**Session context:** Repairing a Windows desktop application's frontend bridge and running its full installer.
**Skill:** managing-build-environments / task-observer
**Type:** internal
**Phase/Area:** Build environment selection

**Issue:** The installer selected an externally managed Python through a globally discoverable `uv` executable and failed before the build. A process-local PATH containing the project's `.venv` and Node runtime, while excluding the external manager, allowed the same installer to complete without changing global configuration.

**Suggested improvement:** Build wrappers should accept an explicit interpreter/manager path or validate that the selected environment belongs to the project before installing dependencies; retain a process-local PATH fallback for legacy batch files.

**Principle:** Reproducible builds require an explicit, project-owned toolchain boundary; a globally discoverable executable is not proof of the correct environment.

### Observation 7: Verify artifact path casing in Git on Windows

**Status:** OPEN
**Date:** 2026-09-27
**Session context:** A loop report was readable locally but absent at the exact path expected by a remote reviewer.
**Skill:** orientacao-rapida
**Type:** internal
**Phase/Area:** Repository handoff verification

**Issue:** Windows resolved `.Codex/` and `.codex/` to the same local directory, while the Git remote treated those as distinct paths. A local existence check passed even though the requested artifact path was absent from the branch.

**Suggested improvement:** When a handoff requires an exact repository path, verify it with `git ls-tree` or `git ls-files` using exact case before reporting the artifact published; confirm the remote path after push.

**Principle:** Case-insensitive local path resolution does not prove the exact artifact path exists in a case-sensitive repository view.
