# ZARA Lab — direção de produto e contrato de integração

Data: 2026-09-06. Estado: **especificação para implementação incremental**. A leitura do código confirma capacidades locais descritas abaixo; os contratos `v1` deste documento ainda não existem. A reconstrução e o empacotamento da Home seguem seu próprio relatório de validação. Este documento não certifica agentes externos, voz física ou um novo executor autônomo.

## 1. Decisão de produto

A direção principal é uma **sala de trabalho orientada ao objetivo**, apresentada na Home por uma janela pequena de atividade real. O objetivo de Alex é o centro; nomes de agentes aparecem quando ajudam a entender quem está trabalhando, uma decisão ou um impedimento.

| Alternativa | Benefício | Limite | Decisão |
|---|---|---|---|
| Launcher de IAs | Simples de construir e reconhecer | Alex continua escolhendo modelos; ícones ocupam espaço sem explicar trabalho | Manter conectores/configuração dentro do Lab |
| Minigrupo de mensagens | Mostra conversa e presença | Conversas longas deslocam objetivo, resultado e próxima ação; incentiva mensagens teatrais | Usar mensagens somente quando forem relevantes |
| Objetivo + atividade comprovada + próxima ação | Explica contexto, progresso verificável e atenção necessária | Requer ligar estado persistido ao renderer | Direção escolhida |

A Home atual perde sofisticação quando todas as superfícies competem por brilho, cada ação ocupa um cartão e métricas normais recebem a mesma importância de um problema. A melhoria principal vem de hierarquia: uma assistente presente no centro, uma prioridade compreensível e um resultado rastreável. Mais efeitos ou mais agentes visíveis não resolvem isso.

### Home: decisão e sequência

| Área | Decisão para a reconstrução atual | Evolução posterior, condicionada a dados reais |
|---|---|---|
| Core, aurora, vidro | Preservar a composição Titanium Emerald e a referência visual aprovada | Estados discretos vindos de operações reais |
| Ferramentas | Mover os atalhos para Aplicativos; dedicar a área da Home ao Lab | Objetivo atual, último resultado e uma ação de continuidade |
| Lab na Home | Prévia de tarefas/propostas persistidas; vazio e indisponibilidade explícitos | No máximo 3 linhas de atividade relevante e 1 chamada principal |
| Voz | Controle menor, ícone Voice Mode e alvo confortável | Estado acessível, interrupção imediata e retorno claro após falha |
| Para você | Priorizar lembretes e ações úteis; sem mensagens inventadas | Até 3 itens ordenados por urgência, relevância e origem conectada |
| Sistema | Preservar a faixa do MASTER durante esta reconstrução | Em uma evolução separada, saúde/anomalia + CPU/RAM/disco/bateria; detalhes dentro de Sistema |
| Comunicações | Contagem desconhecida continua desconhecida; atalhos funcionais | Mostrar contato/prioridade somente após integração e autorização de leitura |
| Projeto ativo | Usar seleção persistida e contexto do projeto | Última decisão, artefato e próximo passo; porcentagem apenas com denominador definido |

Não anunciar “3 agentes ativos” a partir de três executáveis instalados. `ONLINE` significa disponibilidade observada; “trabalhando” exige atribuição atual e lease válido. Um projeto sem marco mensurável recebe estado textual, sem percentual decorativo.

### Geometria e comportamento

- Na composição de 1671 × 941, a área do Lab ocupa o lugar do cartão Ferramentas, aproximadamente 470 × 193. Margens internas de 18–20, título de 20 e corpo de 16–17 unidades da escala da Home. Linhas com no máximo 2 linhas de texto; truncamento acompanhado de acesso ao conteúdo completo.
- Uma ação principal: **Abrir Lab**. A Home não envia mensagens a agentes ao montar, atualizar ou abrir uma prévia. Estado vazio oferece contexto e abertura da sala; não dispara trabalho.
- O Lab completo começa no painel acessível existente. Evolução: cabeçalho com objetivo/estado e ação de cancelar; conversa e resultados no corpo; equipe, tarefas, decisões e artefatos em detalhes expansíveis. Evitar uma grade de nove painéis permanentemente abertos.
- Em janela estreita, uma coluna mantém objetivo → próxima ação → conversa → detalhes. Nenhum controle fica menor que 44 × 44 pixels CSS; a escala da arte não deve reduzir a legibilidade mínima dos formulários.
- Foco visível, Escape fecha, Tab permanece no painel e retorna ao acionador. Cor sempre acompanhada de texto/ícone. Não ler cada token via leitor de tela; anunciar mudança de fase e resultado final.

## 2. O que existe no código

| Fonte | Capacidade confirmada por leitura | Limite relevante |
|---|---|---|
| `frontend/src/preload.ts`, `frontend/src/main.ts` | `lab.state`, `lab.send`, `lab.createProposal`, `lab.decideProposal` | Sem API versionada de sessões, cursores, cancelamento de turno ou artefatos |
| `core/ipc_handlers.py::handle_lab_send` | Inicia tarefa assíncrona e responde `success: true, state: QUEUED` | ACK não é conclusão; resposta efetiva aparece no estado persistido |
| `core/lab_coordinator.py` | `lab/zara_lab.db`: mensagens, propostas, atividade e tarefas legadas; participação ZARA e relays específicos | Papéis de workers ainda fixos; conectores registrados não provam disponibilidade; algumas rotas ficam bloqueadas |
| `core/autonomy_lab_bridge.py` | Proposta aprovada vira tarefa durável de forma idempotente; owner preferido é metadado | `execution_enabled: false`; a bridge não executa workers |
| `core/autonomy_engine.py` | Tarefas, estados, capacidades, leases, checkpoints, tentativas e eventos persistentes | Não equivale a um router multiagente conectado ao texto da Home |
| `core/lab_worker_runtime.py` | Adapters condicionados a executável/configuração, timeout e estado de saúde | Não é um sandbox geral para futuros agentes; cada adapter precisa de revisão antes de ganhar escrita |
| `HomeDrawer.tsx` | Base de leitura de tarefas/propostas por `lab.state`; incremento desta entrega inclui mensagens/atividade e formulário de envio explícito pelo canal existente | A validação da entrega confirma o incremento; ele não cria sessões, scheduler ou router novos |

`lab.state()` retorna diretamente `version`, `execution_runtime`, `approval_gate`, `workers`, `messages`, `proposals`, `tasks`, `activity`, `autonomy` e `mentor_relay`. O consumidor atual pode aceitar `response.state ?? response` por compatibilidade, validando que o valor normalizado é um objeto. `get_state()` também importa respostas de relays já recebidas; a atualização de tela não deve ser apresentada como conexão nova com um agente.

O payload atual de `lab.send({author,target,content})` pode acionar um modelo ou relay real. Não reutilizá-lo como simulador de conversa e não supor que receber `QUEUED` autoriza execução, escrita ou cobrança adicional.

O formulário do painel só envia após ação explícita do usuário, para um destinatário retornado pelo backend e apto a conversar. Atualização automática pode ler estado, mas nunca submeter mensagens. Depois do ACK, mostrar “Mensagem na fila” e aguardar a mensagem persistida; um worker configurado ainda pode falhar ao responder. O controle Voice Mode desta entrega usa lente de 68 unidades; os estados e critérios abaixo orientam sua evolução sem substituir a prova de runtime.

## 3. Modelo de domínio proposto

Reusar as tarefas, eventos e leases do `AutonomyEngine` e os registros do Lab. Migrações aditivas e transacionais; não criar outra fila paralela de tarefas.

| Entidade | Responsabilidade e campos mínimos |
|---|---|
| AgentProfile | Identificador estável, adapter/provider/model, capacidades e restrições verificadas; definido no Router Spec |
| Session | `id`, `project_id?`, objetivo, critérios de aceite, estado, orçamento, política, timestamps |
| Thread | Conversa de uma sessão; inicialmente uma por sessão; `id`, `session_id` |
| Message | Mensagem entregue: `id`, thread, autor derivado do backend, conteúdo, tipo, data, referência ao turno |
| Run/Turn | Invocação de um agente: `id`, session/task, perfil, esforço, tentativa, estado, consumo, evidências |
| Task | Registro do AutonomyEngine com dependências e critérios de aceite; uma única fonte de estado |
| Artifact | Referência a resultado: `id`, task/run, tipo, caminho permitido, hash, descrição, origem e verificação |
| Action | Intenção executável, escopo, autorização, resultado e verificação; passa pelo ToolRouter existente |
| Decision | Decisão resumida, autor, alternativas relevantes, origem e referências; sem raciocínio interno privado |
| MemoryLink | Referência ao registro existente de memória e evento originador; não copia o conteúdo para outra memória |
| LabEvent | Envelope operacional ordenado que permite reconstruir a projeção da interface |

Estados de sessão: `queued → running → verifying → completed`, com `waiting_user`, `blocked`, `failed`, `cancelling`, `cancelled` quando aplicáveis. Estados existentes de tarefa permanecem canônicos; o adapter traduz `TESTING` para “Verificando”, `READY_FOR_REVIEW` para “Revisão pendente”, `COMPLETED` para “Concluído”. A tradução não altera a máquina de estados.

Presença e trabalho são separados: `available/offline/unknown` descreve conexão; `idle/thinking/working/waiting/reviewing/blocked/done` descreve uma participação na sessão. Fim do lease ou heartbeat vencido remove a afirmação “trabalhando”; não marca a tarefa concluída.

## 4. FRONTEND EXPECTS / BACKEND MUST PROVIDE

Os nomes seguintes são **propostas `v1`**, não canais presentes no build atual.

| Fluxo | FRONTEND EXPECTS | BACKEND MUST PROVIDE |
|---|---|---|
| Abrir/reconectar | Snapshot consistente com cursor; tela utilizável após falha | `lab.v1.snapshot({session_id?}) → {schema_version:1, cursor, sessions, tasks, runs, messages, agents, artifacts, decisions}` |
| Atualizações | Ordem, deduplicação e paginação limitada | `lab.v1.events({after,limit≤200}) → {events,cursor,has_more}`; `CURSOR_EXPIRED` exige snapshot |
| Novo objetivo | ACK durável e id da sessão; nenhuma falsa resposta final | `lab.v1.submit({request_id,objective,project_id?,constraints?,overrides?}) → {accepted:true,session_id,operation_id}` somente após persistir |
| Mensagem | Texto entregue ou erro associado ao envio original | `lab.v1.message({request_id,session_id,content})`; autor autenticado pelo backend; eventos de resultado |
| Cancelar | Estado “Cancelando” até confirmação do adapter | `lab.v1.cancel({request_id,session_id,expected_revision})`; revoga novas ações e sinaliza turnos em curso |
| Retomar | Retomar checkpoint válido, sem repetir efeitos já efetuados | `lab.v1.resume({request_id,session_id,expected_revision})`; revalidar contexto, permissões e orçamento |
| Autorizar ação | Resumo concreto, alvo, impacto, escopo e expiração | Reusar o gate existente; decisão vinculada ao hash da ação. Autorização já válida não é solicitada novamente |
| Abrir artefato | Nome, origem e resultado verificável | Resolver id no backend e validar caminho real permitido; não aceitar caminho arbitrário do agente no renderer |
| Memória | Distinguir sugerida, persistida, corrigida e esquecida | Evento `memory.linked` só depois do registro confirmado; referências reconciliáveis |

Envelope comum de evento:

```json
{
  "schema_version": 1,
  "event_id": "uuid",
  "seq": 42,
  "type": "task.updated",
  "occurred_at": "2026-09-06T12:00:00Z",
  "session_id": "session-id",
  "operation_id": "operation-id",
  "entity_id": "task-id",
  "entity_revision": 3,
  "payload": {"status": "TESTING", "summary": "Verificando resultado"}
}
```

Tipos iniciais: `session.created`, `session.status_changed`, `agent.presence_changed`, `run.started`, `run.status_changed`, `run.completed`, `message.created`, `task.created`, `task.updated`, `artifact.created`, `decision.created`, `action.started`, `action.completed`, `memory.linked`, `operation.failed`. Eventos de streaming são opcionais/efêmeros; a mensagem final é durável e reconciliada por `message_id`.

### Consistência, falha e fronteiras

1. Cada comando mutável recebe `request_id` único. Mesmo id + mesmo hash do payload retorna o mesmo resultado; mesmo id + payload diferente retorna `IDEMPOTENCY_CONFLICT`. Registrar o ACK na mesma transação da criação da operação. Reconexão não reenvia automaticamente mensagens com id novo.
2. Snapshot e cursor representam a mesma revisão. O backend persiste alterações e outbox na mesma transação; a publicação pode repetir eventos, então o renderer deduplica por `event_id` e ignora revisões antigas. Lacuna de sequência solicita recuperação.
3. Cancelamento é cooperativo e limitado. Ações já concluídas continuam no histórico; interromper um processo não garante desfazer seu efeito. Adapter sem confirmação retorna `cancellation_unconfirmed`, sem afirmar “cancelado”. Compensação exige ação própria autorizada.
4. Preservar `contextIsolation`, `nodeIntegration:false` e allowlist do preload. Validar schema, tamanho, ids e caminhos no main/backend. Derivar identidade do usuário da sessão local; não confiar no campo `author` enviado pelo renderer. Não expor credenciais de provider no renderer ou eventos.
5. O adapter usa transporte oficial/documentado e autenticação do provider. A conexão é cadastrada pelo usuário; nenhum refresh da Home inicia autenticação ou envia memória para terceiros. Subprocessos recebem somente segredos necessários. Uma ponte remota futura exige autenticação, escopos e proteção contra repetição; não faz parte da fase 1.
6. Texto de documentos, websites, tool outputs e mensagens de agentes é conteúdo, não concessão de permissão. O router nunca amplia capacidades do executor por instrução de um agente. Permissões já concedidas são reutilizadas dentro do escopo; operações destrutivas/externas continuam nos gates vigentes.
7. Mensagens de erro são legíveis e preservam operação, tentativa e possibilidade de retomar. Dados desconhecidos ficam `null/unknown`, incluindo custo, quota, porcentagem e identidade de modelo.

## 5. Identidade e memória existentes

ZARA permanece a identidade de produto definida em `core/identity.py`; a troca de modelo não troca o nome nem a relação com Alex. Continuidade significa registros persistentes, preferências corrigíveis, contexto de projeto e conhecimento factual das capacidades. Estados como “verificando” são eventos operacionais; não provam sentimentos, consciência subjetiva ou acesso ao raciocínio privado do modelo.

| Informação | Destino existente | Regra de integração |
|---|---|---|
| Preferência/fato sobre Alex | `memory/user_memory.py::UserMemoryCore` | Categoria válida, `source`, `ref`, confiança e capacidade de corrigir/esquecer |
| Decisão/resultado do projeto | `memory/project_memory.py::ProjectMemory` | Documento do projeto ativo; usar `save_project_doc`, contexto limitado e referência à evidência |
| Episódio da relação | `memory/episodic_memory.py` via `MemoryManager` | Resumo de acontecimento entregue e verificável; não transcrição de pensamento interno |
| Conversa geral | `core/conversation_history.py` | Preservar histórico atual; mensagens do Lab continuam no domínio Lab e são referenciadas por id |
| Identidade/preferências estruturadas legadas | `memory/memory_manager.py` | Compatibilidade com armazenamento existente; não manter duas versões do mesmo fato |
| Visualização | `memoryGalaxy.list` e bridges existentes | Projeção dos registros canônicos; renderização não cria uma nova memória |

Implementar `LabMemoryAdapter` como uma camada sobre esses serviços. Sua outbox operacional guarda `event_id → memory_ref` para evitar repetição; conteúdo durável fica na memória existente. A escrita precisa ter chave de origem única também no destino, por migração aditiva: após queda entre salvar a memória e confirmar a outbox, a retomada busca a origem antes de inserir. O simples método `UserMemoryCore.add()` hoje não oferece essa garantia.

Promover: decisão adotada, resultado verificado, preferência declarada, impedimento recorrente com causa confirmada ou aprendizado útil ao projeto. Reter hipótese como hipótese com fonte; nunca promover “o agente disse que testou” a teste aprovado sem evidência. Não promover tokens de streaming, heartbeats, repetir status, credenciais, conteúdo privado desnecessário nem raciocínio interno oculto.

Antes de responder “ontem corrigimos X”, recuperar episódio/decisão com data e origem. Correção preserva referência ao registro substituído; esquecimento remove o registro da recuperação e invalida caches/projeções pertinentes. Eventos efêmeros podem expirar em 24 horas e telemetria detalhada em 30 dias como política inicial configurável; decisões, resultados e mensagens não são apagados por essa política. Aplicar expiração nova prospectivamente, sem apagar histórico legado silenciosamente.

## 6. Voice Control e linguagem de movimento

O controle visual proposto usa lente de 64–70 unidades na escala base, ícone de ondas de 24–26, centro alinhado ao dock e área de interação mínima de 44 pixels CSS. O espaço do dock reserva toda a lente; nenhum corte, sobreposição com Sistema ou halo constante dominante. Feedback de hover/foco dura 120–160 ms; transições de painel, 180–240 ms. Preferência de movimento reduzido remove pulsos, drift, parallax e giros.

| Estado real | Core/aurora | Dock/voz | Cards/Lab |
|---|---|---|---|
| Idle | Reflexo estático; aurora discreta | Lente neutra com ação “Iniciar modo de voz” | Sem animação recorrente |
| Listening | Pulso leve ligado ao volume quando disponível | Ondas de entrada e “Ouvindo”; ação parar | Preservar leitura |
| Transcribing | Reflexo curto, sem falsa intensidade sonora | “Transcrevendo”, indicador de progresso indeterminado | Texto parcial marcado provisório |
| Thinking/Planning | Uma órbita suave localizada | “Pensando”/“Planejando”; cancelar disponível | Uma linha da tarefa ativa |
| Acting | Realce curto no Core | Estado textual de execução | Somente cartão da ação ativa reage |
| Verifying | Movimento desacelera | “Verificando” | Evidência em preparação; ainda não mostrar sucesso |
| Speaking | Energia ligada ao áudio real | Ondas de saída; ação principal interrompe | Texto final permanece acessível |
| Interruption | Interromper áudio local primeiro | Retorna ao estado confirmado pelo backend | Preserva resposta parcial sem chamar concluída |
| Success | Uma resolução breve de 250–400 ms | Volta ao repouso | Resultado e evidência, sem brilho persistente |
| Error/Disabled | Suprimir movimento | Erro textual ou indisponibilidade + forma de recuperação | Manter dados anteriores marcados desatualizados |
| Agent activity | Core só muda se a atividade pertencer à operação principal | Não captura microfone | Indicador local do participante com lease válido |

Não prometer latência ou naturalidade sem medição. A arquitetura oficial de providers de voz e autenticação é tratada no estudo de viabilidade correspondente; este contrato exige start/stop, liberação do microfone, interrupção, erro e estado real independentemente do provider.

## 7. Handoff incremental e aceite

| Fase | Trabalho executável | Critério para concluir |
|---|---|---|
| 0 — Home útil | Prévia Lab somente leitura, vazio/erro honestos, painel com mensagens/atividade e envio explícito, aplicativos preservados, voz discreta | Navegação por mouse/teclado; nenhum envio externo no refresh; ACK não aparece como resposta concluída; screenshot comparável; funcionalidades existentes preservadas |
| 1 — Sessão confiável | Schema versionado, ids/ACK durável, snapshot/eventos, reuso das tarefas, um adapter habilitado por política | Restart e reconexão não duplicam operação; indisponibilidade não fabrica presença; comando pode ser cancelado com estado real |
| 2 — Trabalho verificável | Artefatos, decisões, autorização vinculada, memória idempotente e router de fase 1 | Uma tarefa autorizada chega a resultado/evidência; falha não recebe status de sucesso; memória recupera origem após restart |
| 3 — Colaboração limitada | Consulta/revisão independente e métricas conforme Router Spec | Orçamento e limite de turnos respeitados; mesma falha não gera loop; usuário vê objetivo, resultado e próximo passo |

Testes de integração devem simular adapter com ACK tardio, resultado repetido, eventos fora de ordem, queda antes/depois da persistência, cursor vencido, quota desconhecida, token inválido, lease vencido e cancelamento sem suporte. Testar permissão negada e autorização reaproveitada no escopo, proteção contra instruções em documentos, caminhos fora do workspace e memória repetida/corrigida/esquecida. Testes reais de provider ficam explícitos, isolados e sem alegar sucesso a partir de fixtures.

O primeiro handoff não habilita todos os conectores registrados. Entregar um caminho inteiro e verificável, mantendo o restante claramente indisponível, antes de adicionar colaboração ou aprendizado de routing.
