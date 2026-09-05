# ZARA — INCIDENTS

## INC-2026-09-03-001 — Sidecar não emite ready signal

**Causa:** não confirmada. Evidência forte de falha de extração do PyInstaller one-file em runtime; o erro ocorre em `vosk\libvosk.dll` ou módulo `.pyd` do PIL e retorna 127.

**Impacto:** o Electron abre, mas não recebe `SYS: Interface neural pronta`; chamadas IPC iniciais como `engine-list` falham por backend ainda não pronto. Voz, wake gate, lembretes e ações em runtime real ficam não confirmados.

**Correção em andamento:** verificar integridade do executável ou executar rebuild controlado do sidecar; testar standalone no mesmo `cwd`, argumentos e ambiente do Electron; depois revalidar o handshake.

**Prevenção:** manter checkpoint antes de qualquer rebuild, não copiar DLLs ou alterar PATH sem evidência, registrar hash do sidecar, testar o executável em contexto equivalente ao Electron e preservar o baseline de validação.

**ATUALIZAÇÃO 2026-09-04 (execução real, não mais inferência):** a hipótese vosk/PIL estava
errada. Causa real, confirmada rodando o EXE de verdade: `ModuleNotFoundError: No module named
'core.actions.system_advanced'`, porque `build_exe.py` não listava esse módulo (nem
`macro_actions` nem `vision_actions`) em `hiddenimports` — os três são carregados via
`importlib` dinâmico em `core/action_registry.py:697-699`, invisível para a análise estática do
PyInstaller. Corrigido, sidecar recompilado, boot standalone e handshake real com o Electron
empacotado confirmados (ver `.ceo/NIGHT_LOG.md`, entrada 2026-09-04).

**Estado:** RESOLVED_PACKAGED_RUNTIME. Falta confirmação `PHYSICAL_BY_ALEX`.

## INC-2026-09-03-002 — Canal remoto Windows indisponível

**Causa:** não confirmada. As tentativas de execução remota terminaram com pipe fechado/erro de terminal antes de executar os checks.

**Impacto:** não é possível confirmar `git status`, espaço em disco, executar o sidecar Windows ou produzir evidência de build/handshake nesta sessão.

**Correção:** o trabalho seguro continuou por inspeção e documentação no volume montado. Após a reconexão anunciada, três tentativas de comando mínimo (`powershell`, `cmd /c ver` e `cmd.exe` absoluto) ainda terminaram com pipe fechado, sem executar o diagnóstico runtime.

**Prevenção:** não presumir working tree limpo, não executar rebuild ou operações LIVE sem o canal de execução e sem capturar a identidade do candidato.

**Estado:** BLOCKED_REQUIRES_OWNER — reconexão ainda não operacional para execução de comandos.

## INC-2026-08 — Corujão não autorizado

**Causa:** processo externo reescrevia a arquitetura da Zara sem autorização.

**Impacto:** aumento de falhas e risco de regressão.

**Correção:** removido e colocado em quarentena conforme histórico do repositório.

**Prevenção:** uma fonte canônica, ownership por arquivo, checkpoints, validação incremental e nenhuma automação autônoma não autorizada.

**Estado:** MITIGATED; monitorar regressões.
