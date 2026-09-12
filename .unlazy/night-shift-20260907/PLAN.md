# Night Shift 2026-09-07

Goal: close the current Front Brain gate, obtain independent Terra acceptance, then produce and verify one active candidate before advancing to the next safe high-value gate.

## Sequence

1. Finish focused source tests and typecheck.
2. Run one independent Terra medium read-only review limited to the two current blockers.
3. If ACCEPT with P0=0 and P1=0, create exactly one active candidate using the current source.
4. Verify candidate identity and packaged runtime while preserving the existing build as rollback.
5. Continue to the next highest-value gate supported by current evidence.

## Constraints

- No provider calls for the current gate or Terra review.
- No Astra.
- No package before Terra acceptance.
- Preserve unrelated dirty work.
- Stop only for an owner-only blocker, exhausted safe work, or actual quota exhaustion.
