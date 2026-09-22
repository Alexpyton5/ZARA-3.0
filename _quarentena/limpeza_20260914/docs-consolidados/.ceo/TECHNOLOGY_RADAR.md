# ZARA — TECHNOLOGY RADAR

**Atualizado:** 2026-09-03

Este arquivo é o registro vivo de tecnologias candidatas. Nenhuma adoção é presumida sem pesquisa de fonte, sandbox, benchmark, revisão de segurança e regressão.

| Nome | Categoria | Data | Benefício | Risco | Custo de migração | Equivalente atual | Recomendação |
|---|---|---|---|---|---|---|---|
| PyInstaller one-file | Empacotamento | 2026-09-03 | Distribuição de sidecar em um executável | Falha atual de extração de DLL/PYD no runtime | Alto se trocar o formato | `build_exe.py` e runtime existente | INVESTIGAR antes de alterar |
| Electron + React + TypeScript | Desktop/UI | 2026-09-03 | Base existente e funcional para Windows-first | Complexidade de IPC e empacotamento | Muito alto | Stack canônica do projeto | MANTER |
| Gemini Live + Vosk fallback | Voz | 2026-09-03 | Streaming e fallback já previstos | Dependência de hardware/API e validação real pendente | Alto | `core/gemini_live_voice.py`, STT/TTS | MANTER até benchmark |
| Model Router existente | Modelos | 2026-09-03 | Roteamento por capacidade, custo e privacidade | Parte experimental e runtime limitado pelo startup | Médio | `core/model_router.py` | MANTER / AVALIAR |
| ToolRouter + verificadores | Agentes/ferramentas | 2026-09-03 | Execução estruturada com gates e evidência | Cobertura e integração ainda incompletas | Alto para substituir | Arquitetura já implementada | MANTER |

## Pipeline obrigatório

`DESCUBRIR → PESQUISAR → VERIFICAR FONTE → COMPARAR → SANDBOX → BENCHMARK → TESTAR → REVISAR SEGURANÇA → DECIDIR → INTEGRAR → REGRESSÃO → DOCUMENTAR`.
