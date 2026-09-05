# ZARA — CEO BOARD

**Atualizado:** 2026-09-03

| ID | Prioridade | Tarefa | Estado | Definição de pronto |
|---|---:|---|---|---|
| ZARA-P0-01 | P0 | Confirmar integridade do sidecar PyInstaller e o contexto de extração | RESOLVED_PACKAGED_RUNTIME (2026-09-04) | Causa real não era DLL/PYD: `ModuleNotFoundError core.actions.system_advanced` por hiddenimports faltando em `build_exe.py`. Corrigido, ver `.ceo/NIGHT_LOG.md` |
| ZARA-P0-02 | P0 | Revalidar handshake Electron → sidecar | RESOLVED_PACKAGED_RUNTIME (2026-09-04) | `zara-backend.exe` sobreviveu além do timeout de 45s de `startPythonSidecar`; sem isso `main.ts` mataria o processo. Confirmação visual (PHYSICAL_BY_ALEX) ainda pendente |
| ZARA-P0-03 | P0 | Confirmar branch, working tree e espaço do Windows | BLOCKED | Saída verificável do Git e do disco no computador do proprietário |
| ZARA-P1-01 | P1 | Retomar fidelidade visual do Home pelo próximo alvo do quadro existente | TODO | Screenshot Electron real, viewport comparável, build e TypeScript aprovados |
| ZARA-P1-02 | P1 | Validar IPCs e ações críticas no runtime conectado | TODO | Caminho registro → gate → execução → verificação comprovado |
| ZARA-P1-03 | P1 | Auditar memória e automação existentes | TODO | Inventário sem framework duplicado e gaps priorizados |
| ZARA-P1-04 | P1 | Validar voz, microfone e fallback em runtime real | TODO | Wake/listening, interrupção e falha honesta comprovadas |
| ZARA-P2-01 | P2 | Revisar roteamento de modelos e technology radar | TODO | Recomendações com benefício, risco, custo e decisão controlada |

## Regras do quadro

Cada tarefa deve registrar proprietário, arquivos, risco, dependências, validação e evidência. Nenhuma tarefa será marcada como DONE apenas porque uma função retornou sucesso.

## Bloqueios ativos

O canal de execução remota do Windows continua sem responder, impedindo os checks do computador real, a comparação SHA-256 e o teste standalone do sidecar. A configuração foi inspecionada sem alteração de código; o bloqueio de produto permanece a falha de extração do sidecar one-file documentada em `.zara-dev/reports/ZARA-FULL-HEALTH-AUDIT-001.md`.
