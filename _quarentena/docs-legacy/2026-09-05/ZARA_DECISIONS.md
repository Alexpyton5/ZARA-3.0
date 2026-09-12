# ZARA — DECISIONS

**Atualizado:** 2026-09-03

## Decisões permanentes

| Decisão | Motivo |
|---|---|
| Usar o ToolRouter e o registro de ações como caminho canônico | Evita sistemas paralelos e mantém risco, resultado e verificação estruturados |
| Não fabricar telemetria, memória ou sucesso de ações | A interface deve refletir o estado real do computador e do backend |
| Manter o MASTER Titanium Emerald como referência visual | O objetivo é convergência visual, não redesign interpretativo |
| Manter hardware LIVE e Supercérebro desligados por padrão | Reduz risco de ações físicas e destrutivas sem autorização |
| Auditar memória, automação e roteamento existentes antes de reconstruí-los | O repositório já possui implementações e duplicações históricas |
| Fazer uma mudança por vez e validar incrementalmente | Evita regressões e desperdício de tempo/testes |
| Preservar a branch e criar checkpoints antes de mudanças de empacotamento | O histórico registra incidentes de troca de branch e o sidecar é parte crítica do runtime |
| Tratar o baseline de testes como contrato operacional | Falhas conhecidas não devem ser confundidas com regressões novas |
| Não integrar automaticamente modelos ou dependências novas | Novidades devem passar por descoberta, sandbox, benchmark, segurança e regressão |
| Uma tarefa só é DONE com evidência | Build, testes, comportamento e evidência devem corresponder ao pedido |

## Decisão da tomada de controle atual

O primeiro trabalho é o bloqueio de inicialização do sidecar PyInstaller. A ação mínima é diagnosticar a integridade do `zara-backend.exe` e repetir o teste standalone no mesmo contexto do Electron. Não será feita migração de arquitetura, mudança de modelo, alteração de permissões ou redesign visual enquanto o handshake estiver quebrado.

## Decisões pendentes

- Confirmar o estado real do working tree e o espaço livre do Windows.
- Confirmar se o executável está corrompido ou se a extração em `%TEMP%` é bloqueada.
- Escolher entre reconstruir apenas o sidecar ou ajustar o modo de empacotamento, com base na evidência do diagnóstico.
