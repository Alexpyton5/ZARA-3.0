# Gates: front brain UI
OWNS: frontend/src/renderer/components/zara-home/TextCommandInput.tsx, frontend/src/renderer/components/zara-home/BrainSelector.tsx, frontend/src/renderer/components/zara-home/brain-selector.css
Scope: Visible brain selection and truthful submit using existing IPC.

- [x] G1: Renderer typecheck accepts selector and composer contracts
  CHECK: node frontend/node_modules/typescript/bin/tsc --noEmit -p frontend/tsconfig.json
  EXPECT: /^$/
  CWD: C:/Users/alexp/Downloads/ZARA 3.0 CLEAN 002
  EVIDENCE: automatic-evidence=v1; definition-sha256=51042dfb6bb1e06b068ed394b8103fb66804935cc12065b1173fc79a3c41d208; exit=0; EXPECT=matched; output-sha256=e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855; output-bytes=0; shell=C:\Windows\system32\cmd.exe; cwd=C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002; path=199796bfb79d/37 entries

- [x] G2: UI offers Luna/Astra/Sol/Terra with factual state, changes only after successful IPC, preserves draft on failure and uses real send icon
  EVIDENCE: Parent inspected BrainSelector.tsx and TextCommandInput.tsx after the provider-unavailable correction; the four exact options, confirmed selection, retained draft and Send icon are present.
