# Existing Lab integration joins

Evidence level: SOURCE inspection only. This map does not prove runtime, packaged, or physical behavior.

## 1. Public natural-language mission → Autopilot → source mission

- Present: `IPCHandler.handle_lab_v1_autopilot()` validates `intent`, calls
  `LabV1Service.start_autopilot()`, then schedules `run_autopilot()` only after the mission is
  persisted (`core/ipc_handlers.py:3688`; `core/lab_v1/service.py:200,217`).
- Present: `LabV1Service._get_autopilot()` shares one Autopilot instance with
  `AutonomySupervisor` (`service.py:188`). Source-mission selection remains inside that canonical
  Autopilot; there is no second workflow here.
- Missing join: the public `lab-v1-submit` IPC route always returns `workforce_refusal()` and never
  calls `LabV1Service.submit()` (`ipc_handlers.py:3683`; `service.py:316`). The renderer's
  `submit(sessionId,text)` therefore cannot enter or revise a controlled mission.
- Action: route valid initial queued submissions to `service.submit()`; route active mission text
  to the approved same-controller owner-input method once implemented. Keep `lab-v1-autopilot`
  as the direct new-objective entry.

## 2. Background startup and persisted resume

- Present: async IPC initialization creates `LabV1Service` and calls `start_background()`
  (`ipc_handlers.py:1155-1157`). New successful Autopilot starts also call it (`service.py:200-211`).
- Present: `_background_loop()` repeatedly calls `AutonomySupervisor.tick()` off the event loop;
  exceptions become persisted supervisor failure state (`service.py:69-104`).
- Present: `tick()` reads nonterminal `mission_controls`, keeps unsupported legacy rows, and calls
  the shared Autopilot for the first supported mission (`supervisor.py:92-137`). This is the restart
  resume join.
- Risk: service hardcodes `_background_interval = 2.0`, so persisted `cadence_seconds` is ignored
  while that attribute exists (`service.py:60,96`). Source hashing therefore runs every 2 seconds.

## 3. Natural feedback during an active mission

- Present: every persisted user conversation calls `capture_feedback()` when Lab is initialized;
  it records through `FeedbackInbox` (`ipc_handlers.py:1883-1891`; `service.py:151`).
- Missing join: `AutonomySupervisor.tick()` resumes a supported pending mission and returns before
  reading `FeedbackInbox` (`supervisor.py:105-137` versus `148`). `LabV1Service.submit()` also returns
  `MISSION_CONTROLLED` for active missions (`service.py:316-325`). Active feedback cannot revise the
  same mission.
- Action: add the approved transactional `MissionController.submit_owner_input()` path and make
  `service.submit()` use it for active missions; apply at a safe lease boundary with input/plan
  version fencing so pre-feedback results cannot be promoted.

## 4. Research

- Present: `TechnologyScout.run_due()` fetches bounded GitHub release Atom feeds; supervisor turns
  one observed item into a `DAILY_OPPORTUNITY_REVIEW`, verifies it, and leaves it for owner review
  (`scout.py:42-87,115`; `supervisor.py:190-216`).
- Missing join: there is no `research.fetch` controller ACTION. The research worker receives the
  feed excerpt already captured by the scout; it cannot fetch owner URLs, official docs, public
  search metadata, YouTube metadata, or accessible transcripts with receipts.
- Action: add one guarded HTTPS fetch ACTION before researcher work; require URL/title/excerpt/hash/
  dates in receipts and make reviewer claims trace back to those receipts. Keep unavailable media
  explicit rather than synthesizing it.

## 5. Runtime capability gap → capability → retry original request

- Present: `capture_runtime_failure()` persists typed, SHA-deduplicated `CapabilityGap` evidence
  (`service.py:160-186`). Evolution selects up to three existing source paths from those gaps and
  dispatches the same `SELF_IMPROVEMENT` workflow (`evolution.py:125-148,232-248`).
- Missing join: registry-missing actions carry an empty `source_path`, so
  `_runtime_gap_sources()` ignores them. The evidence lacks the original natural-language request
  and durable session/channel/run correlation. No completion path registers the new capability and
  no safe path retries the original request.
- Action: persist original request/session/channel/run; add a bounded planner mapping step from the
  missing action to existing registry/action inventory. After canonical patch→tests→review→candidate,
  register only the verified capability and retry only replay-safe local requests; never replay
  financial, external, destructive, or otherwise effectful requests automatically.

## 6. Daily evolution

- Present: every supervisor tick persists local `core/**` and `memory/**` hashes without provider
  calls; daily dispatch is capped by `max_new_evolution_missions_per_day` and digest deduplication
  (`supervisor.py:92-104,141-187`; `evolution.py:88-122,151-168`).
- Present priority: owner feedback, factual behavior/source observation, then external scout
  (`supervisor.py:148-216`). Runtime gaps with mapped real source are sent as factual evidence;
  generic inspection may honestly finish with no change (`evolution.py:208-268`).
- Missing proof: no integrated evidence yet shows the all-day loop surviving restart, enforcing the
  daily cap, completing a real mission, and remaining deduplicated in the packaged runtime.

## 7. Transactional release

- Present: `ReleaseQueue` enforces ordered persisted gates: governed verified candidate → identified
  package → hash-bound canary → activation → monitor; failed monitoring invokes rollback
  (`release.py:39-117`). `update()` uses `BEGIN IMMEDIATE` for each state transition (`release.py:30`).
- Missing join: service exposes only `ReleaseQueue.snapshot()` (`service.py:279-280`). No production
  caller joins canonical SourceMission candidate output to `schedule()`, `package_ready()`,
  `accept_canary()`, and `promote()`. The only caller found is the manual `tools/autonomy_release.py`.
- Critical incompatibility: `schedule()` still requires legacy `evolution_repairs.REPAIR_ID` plus
  `CANDIDATE_VERIFIED/PACKAGE_PENDING` fields (`release.py:7,39-67`), while current dynamic Evolution
  records canonical workflow/source observations and SourceMission candidate metadata.
- Action: bind ReleaseQueue to the canonical immutable candidate receipt/session identity, then expose
  one service/controller transition that executes all gates. Make activation of source/runtime and
  CURRENT identity one recoverable transaction; rollback both if activation or monitor fails.

## Closure order

1. Join active owner input to the same MissionController with version fencing.
2. Add guarded research receipts and registry-missing capability mapping.
3. Adapt ReleaseQueue scheduling to canonical SourceMission candidate receipts.
4. Run integrated restart, daily cap, capability retry, research, promotion, and rollback proofs.
