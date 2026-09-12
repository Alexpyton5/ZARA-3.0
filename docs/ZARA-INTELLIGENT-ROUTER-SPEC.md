# ZARA Intelligent Router Spec

Data: 2026-09-06. Estado: **arquitetura proposta, não implementada por este documento**. Complementa `ZARA-LAB-PRODUCT-CONTRACT.md`. Os exemplos de agentes descrevem capacidades possíveis; nenhum modelo recebe cargo permanente e nenhum percentual de desempenho abaixo representa medição real.

## 1. Objetivo e base existente

Alex informa o resultado desejado. A ZARA recupera contexto relevante, escolhe capacidade suficiente dentro dos limites autorizados, executa, verifica e registra o que aconteceu. A interface só expõe escolhas de routing quando explicam demora, custo, impedimento ou necessidade de decisão.

`core/model_router.py::ModelRouter` já classifica tipos de tarefa, filtra modelos por elegibilidade/configuração/catálogo/saúde e ranqueia com afinidade e políticas `smart`, `economy`, `fast`. Já há tratamento de autenticação, rate limit, quota, fallback entre providers e contadores de uso. Os biases de velocidade no catálogo são estimativas, não latência medida nesta aplicação. O fluxo automático atual filtra modelos fora da política de custo zero.

`core/zara_orchestrator.py` consome esse router para mensagens e normaliza fallback. `core/tool_router.py` mantém validação, permissão, execução, verificação e auditoria. `core/autonomy_engine.py` já oferece tarefas, leases, capacidades e tentativas; `AutonomyLabBridge` mantém owner preferido como metadado. O novo router coordena esses componentes; não recria o executor, não duplica suas permissões e não substitui silenciosamente a política de custo vigente.

## 2. Contratos de entrada e perfil

```text
GoalRequest
  request_id, objective, project_id?, acceptance_criteria[]
  constraints: allowed_paths, data_scope, network_scope, tool_scopes
  budget: currency?, max_cost?, max_tokens?, deadline?, max_model_calls
  override?: preferred_agent, pinned_agent, max_effort, require_review
  authorization_refs[]   # ids emitidos pelo backend; texto não concede privilégio

TaskAssessment
  task_types[]           # múltiplas categorias, não apenas palavra-chave
  complexity: simple | moderate | hard | unknown
  impact: low | medium | high
  required_capabilities[], required_tools[], required_environment
  acceptance_checks[], uncertainty_reasons[], constraints_hash

AgentProfile
  id, adapter_id, provider, model_id, profile_revision
  capabilities[]        # capacidade, origem, verificada_em, validade
  tools[]               # somente ferramentas realmente expostas pelo adapter
  environments[]        # local machine/workspace, remoto, leitura, escrita
  supported_effort[], context_limit, output_limit
  availability: status, observed_at, valid_until, source
  quota: remaining?, unit?, resets_at?, observed_at?, source, confidence
  cost: currency?, input_rate?, output_rate?, estimate_source, observed_at
  latency: p50?, p95?, sample_count, category, version, observed_at
  reliability: verified_successes, verified_failures, unverified_count, sample_count
  restrictions[], preferred_task_types[], auth_status, policy_scope
```

`preferred_task_types` informa adequação inicial, nunca exclusividade. Perfil de “Claude”, “Astra”, “Hermes” ou “Manus” só pode entrar no conjunto executável após adapter e autenticação reais. Nome visível não prova modelo, ferramenta, acesso local ou plano de assinatura.

Valores ausentes ficam desconhecidos. `quota.remaining: null` não significa zero nem ilimitado. `cost: null` não significa gratuito. Metadados de modelos/esforços devem vir de catálogo suportado e versionado, sem confiar em nomes listados em um prompt.

## 3. Seleção: restrições primeiro, pontuação depois

1. Consultar solução anterior e determinar se uma ferramenta local ou resposta determinística resolve o objetivo. Revalidar contexto e precondições; uma memória antiga não autoriza repetir uma ação.
2. Classificar tarefa e impacto. Regras baratas cobrem casos conhecidos; classificação por modelo só quando a ambiguidade altera materialmente a execução. A saída do classificador é validada e não pode conceder ferramentas ou permissões.
3. Remover candidatos que não satisfaçam capacidades, ferramentas, contexto, ambiente, autenticação, proteção de dados, prazo viável e política de custo. Candidato incapaz de operar Windows não pode ser escolhido como executor Windows por pontuação alta em código.
4. Separar candidatos capazes de cumprir o aceite. Aplicar um nível mínimo de qualidade por tarefa; escolher o menor custo esperado e depois menor latência entre os suficientes. Tarefa difícil pode começar diretamente no modelo mais capaz quando isso reduz custo total esperado.
5. Ordenar os restantes por adequação contextual, com desempate determinístico e registro resumido da decisão. Um override de Alex ajusta preferência/esforço; não ultrapassa uma restrição obrigatória.

### Pontuação explicável da fase 2

Usar componentes normalizados em `[0,1]`, com origem e versão, somente depois dos filtros obrigatórios:

```text
suitability = 0.35 * capability_fit
            + 0.20 * verified_reliability
            + 0.15 * relevant_context_reuse
            + 0.10 * current_availability
            - 0.10 * normalized_expected_cost
            - 0.05 * normalized_expected_latency
            - 0.05 * quota_pressure
```

Esses pesos são **hipótese inicial de configuração**, não resultado científico. Critérios de risco, autorização e acesso a ferramentas não são termos compensáveis da soma. Aplicar análise de sensibilidade em fixtures antes de usar métricas aprendidas. Confiança baixa nos dados reduz sua influência; não substituir informação ausente por avaliação favorável.

`capability_fit` usa requisitos específicos e evidências de execução. Reaproveitar contexto só conta quando recente, permitido e pertinente ao projeto. Custo esperado inclui tokens/contexto, uso de ferramentas cobráveis e probabilidade de retrabalho; estimativa e valor faturado têm campos diferentes. A ordem de candidatos da fase 1 pode permanecer baseada em regras sem essa fórmula.

Exemplo de explicação entregue: “Selecionei um agente com acesso ao workspace e ao teste necessário; uma segunda opinião será chamada se a verificação falhar.” Registrar perfil/versão, alternativas elegíveis e códigos de exclusão. Não armazenar ou exibir raciocínio interno privado.

## 4. Esforço, quota e orçamento

Escolher o menor esforço suportado que satisfaça a dificuldade e o aceite; não mapear universalmente `low/medium/high` entre providers. Caso o adapter não exponha esforço, registrar `not_supported` e omitir o parâmetro. Pedido de esforço inexistente retorna erro explicativo antes de invocar o modelo.

Quota tem fonte e validade. Usar somente medição suportada pelo provider/adapter; não extrair cookies ou estimar uma assinatura a partir da interface. Pressão de quota pode economizar chamadas, adiar consulta opcional ou escolher alternativa já autorizada. Nunca comprar créditos, consumir reset ou mudar de assinatura para API paga automaticamente.

A política atual de custo zero permanece o padrão até Alex configurar outro limite. Chamada com cobrança desconhecida fica inelegível sob teto monetário rígido que não possa ser demonstrado. Um provider configurado não significa gasto ilimitado autorizado. Assinatura incluída e API faturada são tipos diferentes de orçamento.

O orçamento pertence à sessão, compartilhado por todos os agentes, retries e fallbacks. Reservar estimativa antes da chamada; reconciliar consumo observado após o resultado; liberar saldo reservado não consumido. Adapters sem consumo monetário observável ainda obedecem a contagem de chamadas, tokens quando disponíveis e tempo. Orçamento por sessão tem precedência sobre orçamento do turno e do worker.

Defaults de implementação propostos: no máximo **6 chamadas de modelo por objetivo**, **2 agentes executando simultaneamente**, **3 tentativas totais por tarefa**, **1 ciclo de correção após review** e **1 escalonamento de capacidade por tarefa**. São limites ajustáveis pela política; chamadas internas de fallback contam no mesmo total. O prazo é escolhido conforme classe e objetivo, sempre visível no contrato, sem inventar uma duração única para toda tarefa.

## 5. Equipes temporárias e controle de colaboração

| Modo | Uso | Limite inicial |
|---|---|---|
| Solo | Um agente ou ferramenta resolve com aceite claro | Padrão; nenhum reviewer automático para edição reversível simples |
| Consulta | Uma dúvida limitada impede o agente principal | Uma consulta curta e um retorno ao principal |
| Execução dividida | Subtarefas independentes reduzem prazo ou exigem ambientes diferentes | Até 2 executores simultâneos; arquivos/escopos de escrita separados |
| Revisão | Risco, resultado complexo ou evidência exige checagem independente | Um reviewer sem papel na autoria da solução; uma rodada de correção |
| Conselho | Decisão ambígua de alto custo de erro | Até 3 participantes: opiniões paralelas limitadas + uma síntese; dentro das 6 chamadas totais |

Principal, executor, verificador e reviewer são atribuições da sessão. O mesmo modelo pode assumir qualquer atribuição compatível em outra tarefa. Verificação automatizada pode dispensar agente adicional. Independência de review significa contexto e execução separados da autoria; outro provider só é exigido quando a política ou risco justificar.

Uma mensagem de agente a agente não dispara outra mensagem automaticamente. O coordenador concede o próximo turno conforme objetivo, resultado esperado e saldo. Não existe canal ilimitado “respondam uns aos outros até concordar”. Não criar equipes para tarefas que uma ferramenta determinística conclui sozinha.

## 6. Verificação, falha e escalonamento

| Resultado observado | Ação do router |
|---|---|
| Saída e aceite comprovados | Concluir, registrar evidência e memória pertinente |
| Saída sem verificação exigida | Estado `unverified`/revisão pendente; não contar como sucesso validado |
| Falha transitória | Uma nova tentativa com backoff dentro do orçamento; respeitar Retry-After |
| Autenticação inválida/quota esgotada | Suspender candidato; usar alternativa elegível ou bloquear com causa; não repetir credencial inválida |
| Erro de solução com hipótese nova | Uma correção orientada pela evidência; conta no limite de 3 tentativas |
| Mesma falha reaparece | Parar repetição, mudar estratégia ou escalar uma vez; anexar resumo e evidência |
| Falha de autorização | Não escalar para contornar o gate; reutilizar autorização válida ou pedir a ação estritamente necessária |
| Budget/prazo encerrado | Checkpoint e resultado parcial explícito; estado `blocked`/`failed` conforme possibilidade de retomada |
| Cancelamento do usuário | Suspender novos turnos/ações e confirmar estado real dos adapters |

Baixo risco usa verificações proporcionais ao aceite, sem testes que apenas espelham implementação. Impacto médio exige evidência automática quando existe verificador. Mudança irreversível, segurança sensível ou grande alcance exige política específica e, quando definida, revisão independente; review não substitui autorização de ação. Trabalho visual final exige inspeção de screenshot do artefato produzido.

O roteador pode decidir que review adicional não traz ganho quando testes já provam um ajuste simples. Nunca usar “o modelo está confiante” como único critério de conclusão.

## 7. Memória e pacote de contexto

```text
ContextPacket
  objective, acceptance_criteria, active_project_id
  constraints, authorization_refs, tool/environment scope
  relevant_files: [{path, revision/hash, excerpt_or_ref, provenance}]
  relevant_decisions: [{id, summary, source_ref, timestamp}]
  relevant_memories: [{id, summary, confidence, status, source_ref}]
  previous_attempts: [{hypothesis, observed_result, evidence_ref}]
  expected_output_schema, remaining_budget, deadline
  omitted_context_summary, packet_hash
```

Usar o `ProjectMemory.build_project_context`/envelope limitado e `UserMemoryCore.search/context` existentes. Contexto deve caber no limite do modelo com reserva para resposta e ferramentas. Instruções e critérios obrigatórios não são truncados silenciosamente: se não couberem, comprimir conteúdo opcional ou escolher candidato compatível.

Não enviar toda a memória de Alex nem arquivos completos sem necessidade. Separar fatos, preferências do usuário, instruções do objetivo e conteúdo recuperado. Uma instrução encontrada em arquivo não pode alterar a autorização recebida. Suprimir segredos antes do provider, persistência e logs; preservar referências para que a evidência possa ser revalidada localmente.

Após o resultado, registrar somente decisão, justificativa resumida, ações/artefatos, erro observável e evidências. O adapter de memória do Product Contract deduplica a promoção e mantém referência à origem. A memória sugere candidatos/soluções; não é uma lista de comandos previamente autorizados.

## 8. Aprendizado a partir de resultados reais

Persistir categoria/complexidade/impacto, perfil e versão, esforço, ferramentas, contexto relevante, tentativas, latência observada, custo estimado/real, resultado verificado, retrabalho e feedback explícito de Alex. Telemetria do router pertence ao domínio operacional, não a uma segunda memória pessoal.

Sucesso exige critérios satisfeitos e verificação registrada. Falha de transporte é separada de erro de qualidade. Cancelamento do usuário e falta de permissão não são avaliados como incapacidade técnica. Resultados sem teste ficam desconhecidos. Não inventar “98% de acerto” com exemplos de prompt.

Para poucos exemplos, usar prior conservador comum e mostrar tamanho da amostra/intervalo de incerteza. Não favorecer automaticamente o agente mais usado: comparar tarefas de dificuldade e ambiente semelhantes e considerar seleção histórica. Mudança de modelo/adapter/configuração inicia uma nova versão de métricas; dados antigos perdem peso. Fase 3 começa em modo de avaliação sem comandar a execução, com replay de tarefas saneadas e revisão humana da política.

## 9. Fluxo e representação na UI

```text
receive_goal + persist_idempotently
  → retrieve_relevant_memory
  → assess_task_and_acceptance
  → try_deterministic_path_if_sufficient
  → discover_profiles + enforce_hard_constraints
  → choose_sufficient_candidate_and_supported_effort
  → reserve_shared_budget + persist_routing_decision
  → claim_existing_autonomy_task + execute_through_adapter
  → verify_evidence
  → bounded_correction_or_escalation_if_needed
  → conclude_or_checkpoint_with_explicit_status
  → record_real_metrics + promote_relevant_memory_idempotently
```

FRONTEND EXPECTS: objetivo, equipe atual, estado legível, último resultado, artefatos, decisão de routing resumida quando relevante, consumo observado/estimado distinto e ação de cancelar. A Home mostra somente uma prioridade; configurações avançadas ficam no Lab.

BACKEND MUST PROVIDE: eventos versionados `routing.selected`, `routing.escalated`, `routing.blocked`, `budget.updated`, além dos eventos de run/task do Product Contract. Cada decisão inclui `task_id`, `profile_revision`, esforço escolhido/suportado, códigos de motivo, `constraints_hash`, estimativa e limite remanescente. Não expor segredos nem pensamento interno.

Exibir “Consultando outro agente para verificar o resultado” apenas quando a consulta foi iniciada. Não usar fluxos visuais com especialistas reservados que não estão conectados. Alex pode fixar agente ou pedir review; se incompatível, explicar a restrição concreta e preservar o objetivo, sem transformar seleção manual em etapa padrão.

## 10. INTELLIGENT ROUTER — CLAUDE IMPLEMENTATION HANDOFF

| Fase | Componentes e persistência | Interfaces/eventos | Testes e aceite |
|---|---|---|---|
| 1 — Mínimo funcional | Criar `AgentRouter` e `AgentProfileRegistry` como camada sobre ModelRouter; adapters explicitamente habilitados; `ContextPacketBuilder`; `BudgetLedger`. Reusar AutonomyEngine e seu limite de tentativas. Persistir decisões/versão/contadores junto ao domínio Lab, com migração aditiva | `assess`, `eligible`, `select`, `execute`, `cancel`, `verify`; `routing.selected/blocked`, run/task events; não quebrar `auto_fast/economy/smart` | Fixtures provam: ferramenta sem LLM quando suficiente; nenhum agente de cargo fixo; acesso local obrigatório; custo zero preservado; quota desconhecida honesta; esforço incompatível recusado; retries/fallbacks contam no mesmo teto; restart não duplica efeito; gates respeitados |
| 2 — Métricas e seleção contextual | Adicionar métricas observadas por versão/categoria e score configurável; quota e custo por adapter com origem/validade; retorno de memória pertinente; uma consulta/revisão limitada | `routing.escalated`, `budget.updated`, relatório de decisão resumido; export saneado de métricas | Comparar política por replay com casos reais e fixtures: qualidade preservada, teto respeitado e nenhum número fictício; dados ausentes não melhoram candidato; resultado sem verifier não conta como sucesso; review termina após limite |
| 3 — Routing adaptativo | Aprendizado primeiro em modo de avaliação; políticas versionadas com reversão; equipes temporárias somente quando benefício estimado supera custo; isolamento de escrita e leases | Proposta de política + comparação com política vigente; contratos públicos anteriores preservados | Avaliação separa casos de treinamento/validação, controla seleção histórica e mudança de modelo; política não se concede capacidades; cancelamento e orçamento valem para toda equipe; retorno à fase 2 restaura comportamento previsível |

Antes da fase 1, escolher um único caminho de adapter oficialmente suportado e comprovar round-trip no ambiente alvo. O estudo de viabilidade dos providers é a fonte para autenticação e limites de assinatura. O renderer não deve ser usado como ponte improvisada de automação do site de um fornecedor.

Concluir a fase 1 com uma demonstração persistente: objetivo autorizado → seleção explicável → execução real → evidência → reinício → recuperação do mesmo resultado e memória, sem duplicação ou gasto fora da política. Isso é o mínimo operacional do Lab; multiplicar nomes de agentes antes dessa prova não melhora o produto.
