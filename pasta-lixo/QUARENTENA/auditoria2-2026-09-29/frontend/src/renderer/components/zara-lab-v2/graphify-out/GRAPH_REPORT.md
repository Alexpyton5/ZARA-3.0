# Graph Report - frontend\src\renderer\components\zara-lab-v2  (2026-09-15)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 44 nodes · 76 edges · 4 communities
- Extraction: 100% EXTRACTED · 0% INFERRED · 0% AMBIGUOUS
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `48339a3e`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- labTypes.ts
- LabRoom.tsx
- useLabRoom.ts
- LabRoom

## God Nodes (most connected - your core abstractions)
1. `LabRoom()` - 11 edges
2. `useLabRoom()` - 7 edges
3. `asList()` - 5 edges
4. `requireResult()` - 5 edges
5. `failureText()` - 5 edges
6. `Avatar()` - 3 edges
7. `handoffStageLabel()` - 3 edges
8. `reviewVerdictLabel()` - 3 edges
9. `label()` - 3 edges
10. `timestamp()` - 3 edges

## Surprising Connections (you probably didn't know these)
- `LabRoom()` --calls--> `asList()`  [EXTRACTED]
  LabRoom.tsx → labTypes.ts
- `LabRoom()` --calls--> `failureText()`  [EXTRACTED]
  LabRoom.tsx → labTypes.ts
- `LabRoom()` --calls--> `requireResult()`  [EXTRACTED]
  LabRoom.tsx → labTypes.ts
- `LabRoom()` --calls--> `useLabRoom()`  [EXTRACTED]
  LabRoom.tsx → useLabRoom.ts
- `Avatar()` --calls--> `avatarHue()`  [EXTRACTED]
  LabRoom.tsx → labTypes.ts

## Import Cycles
- None detected.

## Communities (4 total, 0 thin omitted)

### Community 0 - "labTypes.ts"
Cohesion: 0.08
Nodes (20): Artifact, Binding, Decision, Handoff, HANDOFF_STAGE_LABELS, LABELS, LabEvent, Message (+12 more)

### Community 1 - "LabRoom.tsx"
Cohesion: 0.38
Nodes (6): Avatar(), parseReview(), Agent, avatarHue(), HANDOFF_STAGES, initials()

### Community 2 - "useLabRoom.ts"
Cohesion: 0.48
Nodes (6): asList(), failureText(), requireResult(), Snapshot, savedRoom(), useLabRoom()

### Community 3 - "LabRoom"
Cohesion: 0.33
Nodes (6): handoffStage(), LabRoom(), handoffStageLabel(), label(), reviewVerdictLabel(), timestamp()

## Knowledge Gaps
- **20 isolated node(s):** `Provider`, `Model`, `Team`, `Binding`, `Message` (+15 more)
  These have ≤1 connection - possible missing edges or undocumented components.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `LabRoom()` connect `LabRoom` to `LabRoom.tsx`, `useLabRoom.ts`?**
  _High betweenness centrality (0.021) - this node is a cross-community bridge._
- **Why does `useLabRoom()` connect `useLabRoom.ts` to `LabRoom.tsx`, `LabRoom`?**
  _High betweenness centrality (0.010) - this node is a cross-community bridge._
- **Why does `initials()` connect `LabRoom.tsx` to `labTypes.ts`?**
  _High betweenness centrality (0.009) - this node is a cross-community bridge._
- **What connects `Provider`, `Model`, `Team` to the rest of the system?**
  _20 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `labTypes.ts` be split into smaller, more focused modules?**
  _Cohesion score 0.08333333333333333 - nodes in this community are weakly interconnected._