# Plan: finish the existing Lab product

Scope: lab-stable
Depth: tree 2
Mode: orchestrated
Contract revision: 1

Interfaces: preserve public Lab IPC and MissionController receipts. Product chooses its team. Source remains frozen through build/canary. Build receipts require completed builder and unchanged inputs; runtime environment excludes builder temp. A4 evidence is historical and untouched.
Toolchain: repository .venv Python, Node, PowerShell, repository root. Native Codex subagents; at most three concurrent leaves. No provider calls until integrated core is stable. Internal unit doubles never count as acceptance evidence. Root independently reviews consequences and real runtime.

| ID | Required outcome or constraint | Owner | Observing gate or manual review | Disposition | Revision |
|---|---|---|---|---|---|
| C1 | Natural input, automatic internal team, real work, review, bounded repair and completion | root | GATES:G1 | ACTIVE | 1 |
| C2 | Complete immutable package, clean runtime temp, real canary | 1.1 | leaf-1.1:G1 and root G2 | ACTIVE | 1 |
| C3 | Background and restart resume without blind uncertain effect repetition | root | GATES:G3 | ACTIVE | 1 |
| C4 | Capability gap installs capability and retries original request | root | GATES:G4 | ACTIVE | 1 |
| C5 | Owner feedback updates same mission | root | GATES:G5 | ACTIVE | 1 |
| C6 | Real research evidence informs engineering | root | GATES:G6 | ACTIVE | 1 |
| C7 | Daily prioritized bounded improvement, measurement and learning | root | GATES:G7 | ACTIVE | 1 |
| C8 | Transactional source/runtime promotion and rollback | root | GATES:G8 | ACTIVE | 1 |
| C9 | New clean packaged mission, one objective and no intervention | root | GATES:G9 | ACTIVE | 1 |
| C10 | One ZARA, CURRENT/data/rollback protected, no Hermes/Manus/Verdent or new paid service | root | GATES:G10 | ACTIVE | 1 |
| C11 | Existing continuation joins identified without project reaudit | 1.2 | leaf-1.2:G1 | ACTIVE | 1 |

## Tree
- 1 integration: GATES.md
  - 1.1 complete immutable builder: gates/leaf-1.1.md
  - 1.2 existing continuation joins: gates/leaf-1.2.md
  - 1.3 natural source scope and safe file support: gates/leaf-1.3.md

| Leaf | Owns | Needs | Tier | Planned wave | State |
|---|---|---|---|---|---|
| 1.1 | tools/build_source_candidate.py, tests/test_build_source_candidate.py | - | judgment | 1 | READY |
| 1.2 | .unlazy/lab-stable/joins.md | - | mechanical | 1 | READY |
| 1.3 | core/lab_v1/source_scope.py, core/lab_v1/candidate_source.py, tests/test_lab_source_scope.py, tests/test_lab_candidate_source.py | - | judgment | 1 | READY |
