# Placar real do Corujão — 22/08/2026

Legenda: **PRONTO** funciona e tem prova; **PARCIAL** existe, mas falta integração ou validação final; **AUSENTE** ainda não foi construído.

## Fase 1 — Fundação

- **PRONTO — auditoria baseline:** `docs/ZARA-BASELINE-AUDIT-001.md`.
- **PRONTO — fronteira entre código e dados:** `core_boundary.md`.
- **PRONTO — snapshot recuperável:** `snapshot_zara.py` e `tests/test_snapshot_zara.py`.
- **PRONTO — três gavetas do cérebro:** `brain/store.py`, `brain/migrate_legacy.py` e seus testes separam memória, conhecimento e skills sem perder a busca.
- **PRONTO — métricas e quadro de trabalho:** `METRICAS-BASELINE.md` e Kanban do Hermes.

## Fase 2 — Cérebro e roteamento

- **PRONTO — capacidades sob demanda:** `core/capability_registry.py`; só 23 ações fundamentais ficam expostas no início.
- **PRONTO — telemetria do roteador:** `core/routing_telemetry.py`; registra executor, modelo, tempo, resultado e fallback. Sugestões exigem revisão humana.
- **PRONTO — portão contra “verde falso”:** `tools/quality_gate.py` e `.quality_gate_baseline.json` protegem 1.294 testes identificados pelo nome.
- **PRONTO — suíte completa:** 1.293 testes passaram e 1 teste de symlink ficou ignorado apenas por falta de privilégio do Windows; zero falhas.
- **PARCIAL — build final:** existem `dist-sidecar/zara-backend.exe` e `frontend/release`, mas o comando único que reinstala, testa e gera tudo do zero ainda precisa ser concluído e executado ponta a ponta.
- **PARCIAL — painel da telemetria:** componente, CSS responsivo e teste estão prontos; falta ligá-lo à tela principal e aos dados reais.

## Fase 3 — Percepção e memória humana

- **PRONTO — sensor de ambiente:** `core/perception/ambiente.py` e `tests/test_ambiente.py`.
- **PRONTO — visão como último recurso:** `core/perception/vision_fallback.py`; ação nativa vem primeiro e visão/OCR só entra com confiança e confirmação adequadas.
- **PRONTO — diário de experiência:** `core/diario_auto.py`; registra uma ocorrência por ação, guarda resultado estruturado, protege segredos e nunca aplica sugestão sozinho.
- **PARCIAL — interface premium:** `frontend/src/renderer/components/zara/PainelAparencia.tsx` existe; ainda falta confirmar sua integração na build distribuída e medir a latência percebida.
- **PARCIAL — revisão formal das fases 1 e 2:** a revisão prática e os testes foram feitos, mas `docs/REVISAO-FASE-1-2.md` ainda não existe.

## Fase 4 — Proatividade e sensação de JARVIS

- **PRONTO — envelope pequeno de contexto:** `core/context_envelope.py` prioriza memória, ambiente e capacidades dentro de um orçamento real.
- **PARCIAL — aprovação pelo celular:** `core/remote_approval_bridge.py` tem autorização autenticada, expiração e consumo único, mas ainda não está ligado ao Telegram e ao executor real.
- **PARCIAL — aprendizado proativo:** o diário já produz candidatos para revisão; ainda falta uma experiência de produto que apresente essas sugestões ao Alex no momento certo.
- **AUSENTE — autonomia graduada completa:** ainda falta unir contexto, risco, confirmação e iniciativa numa política única de níveis de autonomia.

## Fase 5 — Produto distribuível e evolução contínua

- **PRONTO — manifesto seguro do build:** `tools/build_manifest.py` detecta artefato faltando, alterado ou sensível.
- **PRONTO — higiene somente leitura:** `tools/project_hygiene.py` inventaria sobras sem apagar nem mover nada.
- **PARCIAL — distribuição reproduzível:** o instalador atual existe, mas a automação de build em um comando ainda não foi validada do zero.
- **PARCIAL — voz rápida:** `docs/LATENCIA-VOZ.md` localizou a primeira viagem descartada; removê-la com segurança continua bloqueado pela arquitetura da sessão Gemini Live.
- **PARCIAL — caminho 100% gratuito:** há voz e modelos locais, mas a experiência principal ainda precisa funcionar ponta a ponta sem depender da chave do Gemini.

## Próximos três passos

1. Fechar e testar do zero o comando único de build e instalador.
2. Resolver a primeira viagem descartada da voz sem quebrar conversa direta, reconexão ou interrupção.
3. Integrar aprovação pelo celular, sugestões do diário e painel de telemetria numa experiência controlada pelo Alex.
