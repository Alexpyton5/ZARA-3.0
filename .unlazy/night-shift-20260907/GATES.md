# Gates

## G1 — Front Brain closure validation

- Owner: primary Sol implementation task
- Check: focused 124-test Python suite, Node production-validator tests, renderer typecheck, git diff check
- Expected: all exit 0; provider calls remain 0
- Status: PASS (124/124 Python, 5/5 Node, typecheck PASS, diff check PASS)

## G2 — Terra independent limited acceptance

- Depends on: G1
- Owner: Terra medium read-only reviewer
- Check: ACCEPT, P0=0, P1=0 for exactly the two current blockers
- Expected: files modified 0; provider calls 0; no package
- Status: PASS (Terra ACCEPT; P0=0; P1=0; P2=0)

## G3 — Single active candidate

- Depends on: G2
- Owner: build pipeline
- Check: one candidate, recorded source identity and hashes, existing current build retained as rollback
- Expected: candidate builds successfully and is unambiguous
- Status: PASS (one candidate built and exact source/ASAR/backend identities verified)

## G4 — Packaged runtime verification and promotion decision

- Depends on: G3
- Owner: runtime verification pipeline
- Check: candidate identity, startup, IPC/runtime canaries, evidence ledger
- Expected: verification passes before promotion; failures preserve rollback
- Status: PASS_WITH_TRANSIENT (first Lab-open timeout; two subsequent exact-package read-only passes; promotion prohibited by owner)

## G5 — Canonical ONE ZARA

- Depends on: G4
- Owner: Luna read-only inventory, Sol fixes only if a reachable competing official path is proved
- Check: official launcher/runtime paths resolve unambiguously; CURRENT/candidate/rollback/historical classifications recorded
- Expected: one official CURRENT runtime; no destructive cleanup; CURRENT and rollback untouched
- Status: PASS (one official launcher target; legacy packager route closed; CURRENT/candidate remain distinct by role)

## G6 — ZARA Lab functional workforce evidence

- Depends on: G5
- Owner: primary Sol task
- Check: focused Lab unit/integration suite with fake/local adapters only, then compare only remaining gaps to latest workforce checkpoint
- Expected: factual Mission/Team/Agents/Tasks/Runs/Actions/Verification/Memory status; provider calls 0
- Status: PARTIAL_BLOCKED_SAFE (174/174 local Lab tests PASS; packaged Lab room PASS; broad workforce NOT PROVEN because real mission routing does not consume TaskRouter invocation options and no free worker is certified)

## G7 — Cost-safe workforce

- Depends on: G6
- Check: automatic routes use only proven zero-incremental-cost capacity and fail closed otherwise
- Evidence: existing workforce checkpoint; no certification reruns or provider calls
- Status: BLOCKED_SAFE (policy passes and fails closed; no worker is certified LOCAL_FREE/FREE_PROVEN; real mission InvocationOptions binding remains partial)
