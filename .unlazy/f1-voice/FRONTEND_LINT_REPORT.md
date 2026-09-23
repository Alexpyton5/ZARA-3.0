# F1 frontend lint evidence

Toolchain: Node `v24.18.0` at `C:\Users\alexp\AppData\Local\Programs\nodejs\node-v24.18.0-win-x64\node.exe`; npm `12.0.2` at the same Node installation's `npm.cmd`. Worktree dependencies are reached through a junction to the ZARA install with the same `frontend/package-lock.json` SHA-256; no package install or lockfile rewrite occurred.

The full `npm run lint` command exited 1 with **5 errors and 62 warnings**. The F1 source delta from F0 (`30d463a..ba9f866`) changes only `frontend/src/renderer/lib/aecAudio.ts`. All five global errors are in unchanged files:

- `src/renderer/components/zara-home/ActiveProjectCard.tsx:19` — `react-hooks/set-state-in-effect`
- `src/renderer/components/zara-home/BrainSelector.tsx:82` — `react-hooks/set-state-in-effect`
- `src/renderer/components/zara-home/HomeDrawer.tsx:134` — `react-hooks/set-state-in-effect`
- `src/renderer/components/zara-home/SystemPanel.tsx:61` — `react-hooks/set-state-in-effect`
- `src/renderer/components/zara-home/TextCommandInput.tsx:33` — `no-undef`

Focused ESLint on the changed `aecAudio.ts` passed. The official builder's explicit existing-lint option requires the base commit and requires its target list to exactly match the changed frontend files; it reruns ESLint on that delta and records the global failure separately in `BUILD_INFO.json`. This is **not** a claim that the full frontend lint passes.
