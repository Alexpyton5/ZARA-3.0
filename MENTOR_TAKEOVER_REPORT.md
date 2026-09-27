# ZARA 3.0 — relatório de tomada de controle do Mentor

Data: 2026-08-08  
Raiz principal: `C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002`  
Decisão atual: **runtime empacotado certificado no escopo de boot, renderer, backend e IPC inicial**.

## Decisão operacional

A raiz em `C:` é a única fonte de verdade. A antiga candidata `D:\ZARA 3.0 CLEAN 002` e todas as
outras cópias permanecem em standby. O volume `D:` respondeu `Volume - D: está sujo`, portanto não
deve receber instalação, build ou sincronização até reparo administrativo e nova verificação.

## Evidências concluídas

| Área | Resultado comprovado |
|---|---|
| Python | `python -m pytest`: **62 testes PASS**. `compileall` e Ruff: **PASS**. |
| Dependências frontend | `npm ci` e `npm ls`: **PASS**. |
| Qualidade frontend | `npm run typecheck`: **PASS**. `npm run lint`: código `0`, **0 erros e 47 warnings**; warnings permanecem como dívida, não como falha ocultada. |
| Builds frontend | Vite/renderer e TypeScript Electron: **PASS**. |
| Sidecar | PyInstaller/build do backend: **PASS** depois das correções Python e do hotfix SSRF. |
| Empacotamento | `electron-builder`: **PASS** depois da correção early IPC. Instalador e `win-unpacked` foram produzidos. |
| Renderer empacotável | `dist-frontend/index.html` usa `./zara.ico` e `./assets/...` para JavaScript/CSS. |
| Smoke final pós-correção | **PASS**: `ELECTRON_BACKEND_READY=True`, `RENDERER_FAILURE=False`, `BOOT_RACE=False`, stderr `0`. |
| Estado seguro inicial | Supercérebro respondeu `active=false` e `connected=false`; nenhuma capacidade física foi aberta durante o smoke. |

## Hashes finais do pacote certificado

- Sidecar, tanto na origem quanto dentro do pacote:
  `639E4D80FA54C2A50F77EF161D1C0C49AF5CD7FF24638401BD44EAEF9B18BBCC`
- Aplicativo `frontend/release/win-unpacked/ZARA 3.0.exe`:
  `67DC2A7036860A68E5312C212C31B8772AC463ED0289FCC44897867F55075E89`
- Instalador `frontend/release/ZARA 3.0 Setup 3.0.0.exe`:
  `4D63B88D050CF4110D93DBC59D47A21C8E4E191DBA2AC881CFFBF8BD832CEA41`
- `app.asar` associado:
  `E2A536BCC02E6D9D3FD08DDEE543DFB72DD80B42CD0B31CE5E94C90DF16EECCD`

O hash e o tamanho de `dist-sidecar/zara-backend.exe` são idênticos aos de
`frontend/release/win-unpacked/resources/backend/zara-backend.exe`. O timestamp do sidecar é
posterior às mudanças Python incluídas nesta rodada, inclusive confirmação de actions e segurança
de URLs.

## Certificação do runtime e seus limites

O smoke parcial revelou uma corrida: uma requisição IPC inicial podia ocorrer antes de o sidecar
estar pronto. A correção entrou em `frontend/src/main.ts` depois do pacote usado naquele smoke.
Depois disso, Electron TypeScript e `electron-builder` foram executados novamente. A cópia de
`dist-electron/main.js` dentro do novo `app.asar` é idêntica ao arquivo compilado, SHA-256
`A985FE9E7C7AA76F0EE0B52FA7C3AF676D8869522F424CC5062A2EB6DC0B385A`.
O novo `win-unpacked` foi então executado e passou no smoke final sem corrida, stderr ou falha do
renderer. Esse conjunto empacotado está certificado para o escopo exercitado.

Continuam **pendentes de validação humana/online**, sem reduzir o PASS acima:

1. microfone, reprodução de áudio, voz humana e interrupção em dispositivo real;
2. chamadas reais às APIs dos provedores usando as chaves locais, sem expor seus valores;
3. ativação conectada do Supercérebro/Hermes — o smoke confirmou apenas o estado seguro OFF;
4. assinatura para distribuição e primeiro checkpoint Git recuperável.

## Estado de segurança incorporado

- Actions HIGH exigem `confirm=true` booleano em todos os caminhos testados.
- Ações com capacidade física permanecem fechadas sem a autorização correspondente.
- Web fetch de leitura aceita somente GET/HEAD, limita streaming e bloqueia SSRF por scheme,
  userinfo, localhost, redes não públicas, metadata, DNS, peer e redirects.
- Browser e download reutilizam a proteção de URL; os testes web são mockados e não acessam rede.
- Segredos locais continuam fora do Git; valores não devem aparecer em logs ou relatórios.

O plano vivo, backups, gates e protocolo estão em [OPERATIONS.md](./OPERATIONS.md).
