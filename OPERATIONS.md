# ZARA 3.0 — quadro operacional do Mentor

Atualizado em: 2026-08-28
Estado global: **RUNTIME EMPACOTADO CERTIFICADO NO ESCOPO DO SMOKE; VOZ HUMANA/APIS REAIS PENDENTES**.

Este arquivo é a fonte de verdade para prioridade, promoção e recuperação. Um item só recebe
`PASS` quando houver comando concluído e evidência produzida na revisão atual.

## 1. Raiz principal e áreas em standby

**Única raiz principal de código:**

`C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002`

Somente essa raiz pode receber correções, novas implementações, testes e builds. As árvores abaixo
são **STANDBY / ROLLBACK**: não editar, não instalar dependências e não gerar builds nelas.

- `D:\ZARA 3.0 CLEAN 002` — antiga candidata; standby bloqueado porque o volume `D:` está sujo.
- `D:\ZARA_3.0_SAFE_BASELINE_2026-08-08` — baseline de recuperação, somente leitura.
- `D:\ZARA 3.0 CLEAN 002_backup_2026-08-08_11-34-33`
- `D:\ZARA 3.0 WORKING STABLE`
- `D:\ZARA 3.0`
- `D:\ZARA 2 - BACKUP 4`
- `C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002_BACKUP_20260807_133059`
- `C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002_BACKUP_20260807_184724`
- `C:\Users\alexp\Downloads\ZARA 3.0`
- `C:\Users\alexp\Downloads\ZARA 2 - BACKUP 4`
- `C:\Users\alexp\AppData\Local\Programs\zara-frontend` — instalação anterior; runtime standby,
  nunca fonte de código.

Diretórios de dados sob `AppData`, especialmente `C:\Users\alexp\AppData\Local\ZARA3` e
`C:\Users\alexp\AppData\Roaming\zara-frontend`, devem ser preservados. Eles contêm estado de
execução, memória/configuração ou cache; não são backups de fonte e não devem ser copiados
integralmente para o repositório.

### Regra de recuperação

Uma restauração deve copiar a origem standby para uma pasta temporária, gerar um diff revisado e
transferir apenas os arquivos aprovados. Nunca sincronizar uma cópia inteira por cima da raiz
principal e nunca promover por timestamp. A promoção exige os gates da seção 5.

## 2. Bloqueio do volume `D:`

Na auditoria, `fsutil dirty query D:` respondeu `Volume - D: está sujo`. Não executar `npm ci`,
build, empacotamento, instalação ou cópias extensas nesse volume.

O reparo fica fora do fluxo atual da ZARA e requer uma janela administrativa:

1. Fechar processos que escrevam em `D:`.
2. Em terminal administrativo, executar `chkdsk D: /scan`.
3. Se solicitado pelo Windows, executar `chkdsk D: /f` na janela indicada pelo sistema.
4. Confirmar depois com `fsutil dirty query D:` que o volume não está mais sujo.

Não foi executado reparo automático. A consulta equivalente em `C:` retornou acesso negado sem
elevação; portanto este documento não declara o estado dirty/clean de `C:`.

## 3. Matriz fonte → build → runtime

| Camada | Fonte canônica | Saída gerada | Runtime | Estado observado |
|---|---|---|---|---|
| Backend Python | `main.py`, `core/`, `integrations/`, `memory/` | `dist-sidecar/zara-backend.exe` via `build_exe.py` | `resources/backend/zara-backend.exe` no pacote | **BUILD PASS**: sidecar posterior às mudanças Python; SHA-256 `639E4D80…BBCC`, idêntico dentro do pacote. |
| Renderer React/Vite | `frontend/src/`, `frontend/index.html`, `frontend/vite.config.ts` | `frontend/dist-frontend/` | conteúdo do `app.asar` | **BUILD PASS**: Vite concluído e HTML atual usa caminhos relativos `./assets/...`. |
| Processo Electron | `frontend/src/main.ts` e configuração do pacote | `frontend/dist-electron/` | `frontend/release/win-unpacked/ZARA 3.0.exe` e instalador | **BUILD + SMOKE PASS**: correção early IPC empacotada; backend ready, renderer sem failure, sem boot race e stderr zero. |
| Configuração e segredos | `config/*.example.json`; segredo real apenas local | nenhuma | arquivo local / `LOCALAPPDATA` | `config/api_keys.json` existe e está ignorado pelo Git. Nunca imprimir, documentar ou versionar seu conteúdo. |
| Histórico | repositório Git da raiz principal | commits/tags | rollback por commit + baseline externo | **INCOMPLETO**: branch `main` ainda não possui commits e os arquivos aparecem como não rastreados. |

Arquivos em `build-sidecar/`, `dist-sidecar/`, `frontend/dist-*` e `frontend/release/` são derivados.
Não corrigir código diretamente neles.

## 4. Estado real dos checks

| Check | Estado nesta raiz | Evidência atual |
|---|---|---|
| `npm ci` / `npm ls` | **PASS** | Instalação pelo lockfile e árvore de dependências concluídas. |
| `npm run typecheck` | **PASS** | Código de saída `0`. |
| `npm run lint` | **PASS COM DÍVIDA** | Código `0`; 0 erros e 47 warnings. |
| `python -m compileall ...` | **PASS** | Revisão Python atual compilada. |
| `python -m pytest` | **PASS PARCIAL** | 2026-08-28: 1323/1444 passaram, 94 falharam (baseline conhecida), 27 pulados. Nos dias anteriores foi corrigido o bug de `core/action_registry.py` (descartava argumentos posicionais) e removido um sistema não autorizado ("Corujão", um processo Codex que vinha rodando dentro da Zara sem permissão) que tinha ficado pela metade — a suíte melhorou depois da remoção, não piorou. Lista exata das falhas conhecidas em `.known_failures.json`, mantida pelo gate `scripts/debug/nightly_regression.py`. "62 testes" era o total de uma raiz muito mais antiga. |
| `python -m ruff check ...` | **PASS** | Gate Python concluído; hotfix SSRF também validado de forma direcionada. |
| build do sidecar | **PASS** | Hash fonte e empacotado: `639E4D80FA54C2A50F77EF161D1C0C49AF5CD7FF24638401BD44EAEF9B18BBCC`. |
| Vite / Electron TypeScript | **PASS** | Renderer e processo Electron compilados. |
| `electron-builder` | **PASS** | Pacote pós-correção produzido; sidecar e `dist-electron/main.js` empacotados conferem com suas origens. |
| smoke do pacote anterior | **SUPERADO** | Revelou a corrida early IPC que foi corrigida e reempacotada. |
| smoke final pós-correção | **PASS** | `ELECTRON_BACKEND_READY=True`, `RENDERER_FAILURE=False`, `BOOT_RACE=False`, stderr `0`. |
| Supercérebro no smoke | **PASS SEGURO OFF** | `active=false`, `connected=false`; ativação real/Hermes continua pendente. |
| voz humana / APIs reais | **PENDENTE** | Exigem dispositivo, audição humana e chamadas online controladas. |

Relatórios `MENTOR_*` são histórico e contexto; não substituem evidência da revisão atual.

## 5. Lista de tarefas priorizada

### P0 — obter uma baseline reproduzível e segura

- [x] **P0-01 — Definir uma única raiz principal.** A raiz em `C:` foi escolhida; todas as demais
  ficam em standby.
- [x] **P0-02 — Recuperar dependências e gates frontend.** `npm ci`, `npm ls`, typecheck e builds PASS;
  lint com 0 erros e 47 warnings conhecidos.
- [x] **P0-03 — Reconciliar correções críticas na raiz C.** Policy HIGH/capability, testes IPC e
  hotfix SSRF estão incorporados sem copiar builds antigos.
- [x] **P0-04 — Restaurar e executar a suíte de testes.** Histórico: 62 testes PASS. Atual
  (2026-08-28): 1323/1444 PASS, 94 falhas conhecidas (ver linha `python -m pytest` na tabela
  de checks acima), 27 pulados.
- [x] **P0-05 — Executar gates Python.** Compileall e Ruff PASS.
- [ ] **P0-06 — Criar o primeiro marco Git recuperável.** Verificar segredos e derivados; após os
  gates verdes, registrar commit baseline e tag com data/build ID.
- [x] **P0-07 — Reempacotar após a correção early IPC.** Novo `app.asar`, `win-unpacked` e instalador
  produzidos; `main.js` empacotado é byte a byte idêntico ao compilado.
- [x] **P0-08 — Executar smoke final pós-correção.** Backend ready, renderer sem failure, zero boot
  race e stderr zero; Supercérebro permaneceu OFF/desconectado com segurança.
- [ ] **P0-09 — Criar checkpoint Git e manifesto de distribuição.** Os hashes finais estão no
  `MENTOR_TAKEOVER_REPORT.md`; ainda falta o primeiro commit/tag recuperável e assinatura.

### P1 — robustez operacional

- [ ] Definir migração e compatibilidade de dados em `LOCALAPPDATA`, sem sobrescrever memórias.
- [ ] Adicionar testes de contrato IPC e de falhas do sidecar/renderer.
- [ ] Consolidar logs de boot, crash e actions com redação de segredos.
- [ ] Testar engines com chaves presentes/ausentes, sem expor valores ao renderer ou logs.
- [ ] Validar microfone, voz humana, reprodução, interrupção e dispositivos indisponíveis.
- [ ] Validar chamadas reais de API e ativação Hermes/Supercérebro com segredos redigidos.
- [ ] Remover divergências entre documentação, `CLEAN_BUILD_ID.txt`, versão do pacote e release.
- [ ] Tratar o arquivo residual `nul` sem operação destrutiva até confirmar origem e impacto.

### P2 — novas implementações depois da estabilização

- [ ] Conectar a Memory Galaxy a um vault real com backup, índice e migração controlados.
- [ ] Completar o conselho/agentes 24/7 com fila de propostas e aprovação explícita.
- [ ] Evoluir autonomia somente sobre actions registradas, auditáveis e reversíveis.
- [ ] Preparar assinatura do executável e canal de atualização com rollback verificável.

## 6. Gates para promover

Executar na raiz principal e guardar a saída:

```powershell
python -m compileall -q main.py core integrations memory
python -m pytest
python -m ruff check .

Set-Location frontend
npm ci
npm run typecheck
npm run lint
Set-Location ..

python build_exe.py
Set-Location frontend
npm run electron:build
```

Em seguida:

1. Conferir que `dist-frontend/index.html` referencia `./assets/`.
2. Confirmar que o pacote contém exatamente o sidecar recém-gerado.
3. Rodar `frontend/release/win-unpacked/ZARA 3.0.exe` e executar o smoke test P0-08.
4. Gerar hashes e registrar a evidência vinculada ao commit/tag.

## 7. Protocolo seguro da equipe autônoma

1. Trabalhar somente na raiz principal e em mudanças pequenas e revisáveis.
2. Antes de editar, inspecionar o estado atual; nunca apagar ou substituir trabalho sem diff.
3. Executar o teste mais próximo após cada correção e o conjunto completo antes de empacotar.
4. Não revelar segredos: verificar somente presença; redigir tokens, headers e payloads sensíveis.
5. Actions HIGH exigem confirmação explícita em toda execução. Ausência ou ambiguidade significa negar.
6. Não modificar backups, instalações standby, dados do usuário ou sistemas externos em testes.
7. Não promover por aparência, timestamp ou existência de EXE; promover somente pelos gates.
8. Parar diante de corrupção de filesystem, necessidade administrativa, perda potencial de dados ou
   dúvida sobre a raiz alvo. Registrar o bloqueio e preservar o rollback.
