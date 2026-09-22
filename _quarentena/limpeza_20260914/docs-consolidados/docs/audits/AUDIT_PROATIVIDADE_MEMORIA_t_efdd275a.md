# Auditoria de Proatividade e Memória da ZARA [continuidade 137]

## FEITO

- [x] Auditada a proatividade (InitiativeEngine) e a memória (long_term, episódica, user_facts) da ZARA.
- [x] Identificados placeholders na proatividade: `_get_utility` retorna 0.5 (hardcoded) e `_get_advice` retorna texto estático "Lembrete: basta um pequeno passo para começar."
- [x] Verificado que o InitiativeEngine não é iniciado pelo ZaraOrchestrator (initialize() só bootstraps identity e model router).
- [x] Verificada a estrutura da memória de longo termo (long_term.json) — contém apenas estrutura vazia sem dados populados.
- [x] Verificada a memória episódica (EpisodicMemory) — 4 episódios armazenados, mas sem relação clara com iniciativa proativa.
- [x] Verificada a user_memory (user_facts.db) — 9 fatos cadastrados nas categorias: preference (5), relationship (1), semantic_fact (1 confirmed, 3 forgotten, 1 confirmed).
- [x] Confirmado que o diário automático (save_session_summary) não tem sido integrado ao InitiativeEngine.
- [x] Verificado o config threshold: InitiativeConfig tem utility_threshold=0.7, mas _get_utility() retorna 0.5.

## NAO FEITO

- [ ] Iniciar o InitiativeEngine no ZaraOrchestrator.initialize.
- [ ] Implementar InitiativeEngine._get_utility para combinar sinais de memória (lições recentes do DiarioAuto ou Aprendizado), contexto (envelope do ContextEnvelope) e estado do usuário.
- [ ] Implementar InitiativeEngine._get_advice para gerar conselho baseado em padrões aprendidos (usando dados do DiarioAuto ou Aprendizado).
- [ ] Popular a memória de longo termo com informações úteis das interações do usuário e da memória episódica.
- [ ] Integrar a memória episódica e semantic_fact no _check_and_act do InitiativeEngine para decisões proativas informadas.

## BLOQUEIO

- [x] InitiativeEngine não é registrado nem chamado no ZaraOrchestrator — engine nunca inicia, então _get_utility e _get_advice nunca são executados no fluxo real.
- [x] Placeholders hardcoded impedem decisões baseadas em contexto real de memória.
- [x] Memória longa vazia não fornece subsídios para utilidade ou advice personalizado.

## PROXIMO

- [ ] Iniciar o InitiativeEngine em ZaraOrchestrator.initialize (core/zara_orchestrator.py) após o boot de identity e model_router.
- [ ] Substituir _get_utility por implementação que pesquise memória episódica, fatos semânticos do usuário e contexto recente para calcular utilidade real (0.0 a 1.0).
- [ ] Substituir _get_advice por implementação que selecione sugestão baseada em padrões aprendidos da memória episódica e fatos confirmados do usuário.
- [ ] Integrar save_session_summary e registro de episódios no InitiativeEngine loop para aprendizagem contínua.
- [ ] Garantir que a memória de longo termo seja preenchida gradualmente com insights relevantes das interações.

## EVIDENCIA ARQUIVOS

- core/initiative/engine.py: linhas 106-112 (_get_utility hardcoded 0.5), linhas 114-119 (_get_advice static)
- core/zara_orchestrator.py: initialize() não chama InitiativeEngine.start()
- core/initiative/config.py: utility_threshold=0.7 desrespeitado por _get_utility
- memory/long_term.json: estrutura vazia sem dados populados
- memory/episodic_memory.py: 4 episódios armazenados
- memory/user_memory.py: 9 user_facts cadastrados