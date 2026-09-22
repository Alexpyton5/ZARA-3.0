# ANÁLISE DA EQUIPE — ZARA 3.0 (2026-09-22)

Análise read-only por 4 agentes (Arquiteto, Engenheiro, Crítico, Reviewer),
consolidada pelo CoS. Correções aplicadas no mesmo dia, em commits próprios.

## O QUE A ZARA É (mapa real)

- **Frontend Electron**: `frontend/src/main.ts` (spawn do sidecar Python,
  protocolo JSON-lines via stdin/stdout) + preload → renderer React/TS.
- **Backend Python**: `main.py` → `core/ipc_handlers.py` (~6.100 linhas,
  63 handlers) — texto, voz, ações, lab, lembretes, segurança.
- **Voz**: `core/gemini_live_voice.py` (Kore) + `voice_stt.py` + `voice_tts.py`.
- **Lab de agentes**: `core/lab_v1/` (50+ arquivos; service, runtime,
  mission_controller) + autopilot de fundo ativado por padrão.
- **Memória**: `memory/` (9 módulos) + camadas paralelas em core/ e memory_system/.

## CAUSA RAIZ DO "NADA MUDA" (confirmada)

O app roda **empacotado** (`frontend/release3/win-unpacked`). Mudanças no
código fonte Python não afetam o exe — precisa reconstruir o
`zara-backend.exe` (PyInstaller) e copiar para
`resources\backend\zara-backend.exe`. O seletor de cérebros do app mescla
dinamicamente o que o backend manda (BrainSelector.tsx) — o problema nunca
foi o frontend.

## CAUSA RAIZ DA CONVERSA SEM RESPOSTA (confirmada em 16:25)

Dois bugs em cadeia, ambos corrigidos:

1. **Cota do codex não engatava o fallback** — o codex falha com o código
   compacto `CODEX_USAGELIMITEXCEEDED` (availability `QUOTA_EXHAUSTED`);
   o passe de reposição só casava marcadores de texto ('quota', 'rate
   limit') que não cobrem esse vocabulário. Corrigido (8ca5d10): o passe
   também casa nos estados de conta pela availability classificada.
2. **A tela rejeitava a resposta de fallback** — no
   `validateFrontBrainProvenance`, a checagem `engine !== selected` rodava
   ANTES da validação do fallback: com fallback factual o engine executado
   É o transporte alternativo, então toda resposta de fallback era
   rejeitada pela tela ("O backend respondeu com X em vez de Y").
   Corrigido (8dde2d8): a validação do fallback roda antes; sem fallback,
   mismatch continua sendo rejeição.

## BUGS CORRIGIDOS (commits 7a65f23 e 40222c5)

1. **Cérebro GLM invisível** — `front_brain.py`: `endswith('/glm-5.3-flash')`
   nunca casava (o id real termina sem a barra). Prioridade agora: modelos
   `-free` primeiro, depois GLM.
2. **OpenCode morto no empacotado** — `shutil.which("opencode")` não achava
   o CLI (é `.cmd` na pasta nodejs, fora do PATH do processo spawnado pelo
   Electron). Corrigido com candidatos explícitos (mesma pasta do harness)
   + leitura do cache como fallback (`_load_catalog` gravava o cache mas
   nunca o lia).
3. **Config invisível ao exe** — o empacotado lê config de
   `%LOCALAPPDATA%\ZARA3\config` (não existia). Semente no primeiro boot:
   `api_keys.json` + `feature_flags.json` congelados dentro do exe.
4. **Voz Kore silenciosa** — chave Gemini só vinha do env; agora com
   fallback no config do usuário.
5. **Lab sem chaves** — `_keys()` só lia o config; agora com fallback no env.
   Workers do Lab reportam estado correto.

## EMBARAÇALHOS ESTRUTURAIS (top 5, para depois)

1. `core/ipc_handlers.py`: god file (6.100 linhas, 63 handlers) — fatiar
   em routers por domínio.
2. Lab triplicado: `lab_v1/` vs `lab_coordinator.py` vs `lab_worker_runtime.py`
   vs `autonomy_lab_bridge.py` — colapsar em lab_v1 + adapters finos.
3. Memória em 4 lugares sem facade único — unificar atrás de `memory/`.
4. Voz sem fronteira: engines em `voice/`, STT/TTS em `core/` — consolidar.
5. Frontend: 3 famílias de componentes (só `zara-home/` é montada) —
   deletar órfãos `zara/interface/` e unificar Header/Dashboard.

## LIXO CONFIRMADO (limpeza separada, com backup)

- Raiz: ~45 arquivos soltos (8 probe_*.py, ~25 dumps .txt, 6 build-*.log).
- `frontend/`: 8 pastas `.current-build-staging-*`, release/ + release2/.
- `core/`: 10 stubs só-comentário, 3 tool_verifiers nunca importados,
  `.bak` files dentro do pacote, `memory_system/` inteiro nunca importado.
- `scripts/fix/`: 30 patches one-off.

## GOVERNANÇA RESTAURADA

`.claude/` (ORG, WORKING_MODEL, CURRENT_MISSION, TASK_BOARD, DECISIONS)
estava deletado na árvore de trabalho — restaurado do git (commit pendente
de conferência).

## RISCOS PERMANENTES

1. Empacotado ≠ source: sempre reconstruir o sidecar e conferir SHA256
   antes de testar físico.
2. Voz (AEC/wake): mudanças exigem teste físico do dono.
3. Autoridade V1 (supersessão de missões): não tocar sem os 60 testes.
