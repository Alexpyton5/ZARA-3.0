# Plano Mestre ZARA — Autopilot rumo a uma assistente de sistema

## Visão executiva

A ZARA deve evoluir de um assistente com ações controladas para uma **camada inteligente de operação do computador**. Ela deverá entender pedidos, descobrir contexto, planejar tarefas, executar apenas o que a política permite, verificar o resultado, aprender com o histórico e propor melhorias. O objetivo não é dar liberdade irrestrita ao código. O objetivo é aumentar muito a capacidade sem perder controle, rastreabilidade e possibilidade de desfazer.

A expressão **“700 vezes melhor”** será tratada como uma meta de produto, não como uma promessa matemática. A melhoria será medida por sete resultados: mais tarefas concluídas, menos erros, menor tempo de resposta, melhor memória, mais integrações, recuperação automática de falhas e maior segurança.

O plano é ambicioso, mas deve ser executado em pequenas entregas. Nenhuma fase pode declarar o sistema pronto sem o teste correspondente. O Windows real, o Electron empacotado, o microfone, o navegador e os provedores precisam ser testados no ambiente físico antes de receberem o estado **Pronto**.

## Regras que não mudam

A ZARA não executará código encontrado na internet automaticamente. Toda descoberta será tratada como proposta. Toda Skill terá versão, permissões, testes, evidências, aprovação e rollback.

O Lab poderá trabalhar continuamente enquanto o processo da ZARA estiver vivo. Isso não será descrito como 24/7 independente enquanto não existir um serviço do Windows ou outro mecanismo de reinício comprovado. O processo deverá pausar em erro, falta de evidência, orçamento esgotado, conflito de arquivos ou perda do volume.

A ZARA usará um único executor de ações. Não serão criados executores paralelos que possam contornar o `ActionRegistry`, o `ToolRouter`, as confirmações ou os verificadores.

A memória terá fontes separadas. O SQLite será a memória operacional. A memória do projeto será a fonte estruturada de contexto. O Obsidian será o espelho humano e pesquisável. Nenhuma dessas fontes deverá ser tratada como prova de que uma ação foi executada.

## Resultado final desejado

Quando as fases principais estiverem completas, o usuário deverá poder dizer algo como:

> “ZARA, organize a pasta do projeto X, encontre documentos repetidos, faça uma proposta, mova apenas os arquivos aprovados, registre tudo e me mostre o relatório.”

A ZARA deverá responder com um plano curto, informar riscos, pedir aprovação somente quando necessário, executar em etapas, confirmar cada mudança, registrar os resultados e desfazer as alterações se a verificação falhar.

Também deverá ser possível dizer:

> “ZARA, pesquise como resolver este problema, compare fontes, crie uma Skill candidata, teste-a sem tocar na produção e me entregue para aprovação.”

Nesse caso, a pesquisa, o resumo, o teste e a proposta serão automáticos. A ativação continuará governada.

## Arquitetura-alvo

A evolução será organizada em dez camadas:

1. **Voz e conversa:** captura, transcrição, interrupção, resposta falada e confirmação.
2. **Entendimento:** intenção, entidades, projeto ativo, urgência e risco.
3. **Memória:** fatos, preferências, tarefas, projetos, decisões e episódios.
4. **Planejamento:** decomposição em passos finitos, limites, prazos e dependências.
5. **Execução:** ações Windows, navegador, arquivos, mídia, agenda e integrações.
6. **Verificação:** evidência pós-ação, estado esperado, screenshot ou leitura do sistema.
7. **Aprendizado:** avaliação de resultado, correção de planos e atualização de memória.
8. **Lab:** pesquisa, arquitetura, codificação, testes, revisão e aprovação.
9. **Release:** sandbox, baseline, candidato, pacote, canário, aprovação e rollback.
10. **Observabilidade:** saúde, logs úteis, métricas, auditoria, alertas e diagnóstico.

## Fase 0 — Congelamento e organização do projeto

**Objetivo:** criar uma base limpa para todas as fases seguintes.

O projeto deverá ter um mapa oficial contendo a finalidade de cada pasta, a fonte de verdade de cada subsistema, os comandos de teste, os scripts de build, os arquivos ativos e a quarentena. A raiz deverá conter somente entradas que uma pessoa consiga identificar rapidamente.

Logs antigos, staging incompleto, caches, duplicatas aparentes e artefatos de diagnóstico deverão ser classificados. A primeira ação será mover para `_quarentena` com um inventário e hash. Exclusão só poderá ocorrer depois de um prazo definido e de uma verificação de que nenhum build, teste ou script depende do arquivo.

**Pronto quando:** a raiz tiver inventário, a quarentena tiver índice, o build ativo estiver identificado e nenhum arquivo de produção tiver sido movido sem registro.

## Fase 1 — Contratos do núcleo

**Objetivo:** reduzir comportamentos diferentes entre módulos.

Criar contratos únicos para intenção, missão, ação, evidência, receipt, Skill, mensagem do Lab, erro e estado de saúde. Cada operação deverá possuir `request_id`, origem, horário, política aplicada, resultado e evidência.

Unificar nomenclatura de estados. Separar claramente “recebido”, “planejado”, “executado”, “verificado”, “aprovado”, “ativado” e “rollback”. Impedir que uma interface mostre “sucesso” apenas porque recebeu um ACK.

**Pronto quando:** backend, IPC e frontend usarem os mesmos estados e os testes rejeitarem transições inválidas.

## Fase 2 — Autopilot supervisionado

**Objetivo:** tornar o ciclo contínuo realmente observável e recuperável.

Evoluir o ciclo `observar → planejar → executar → verificar → aprender → propor` com orçamento, prioridades, deduplicação, backoff, deadlines, leases, cancelamento e pausa global.

Adicionar um painel de saúde com estado do supervisor, última execução, próxima execução, orçamento restante, erros recentes e missões bloqueadas. Criar um botão de pausa geral e uma fila de retomada após reinício.

O Autopilot deverá distinguir três modos: **assistido**, **autopilot governado** e **somente observação**. A mudança para um modo mais permissivo deverá ser explícita e registrada.

**Pronto quando:** o sistema puder executar uma missão pequena, interrompê-la, retomá-la, deduplicá-la e explicar por que uma missão foi bloqueada.

## Fase 3 — Segundo cérebro confiável

**Objetivo:** transformar a memória em contexto útil, não apenas em arquivos guardados.

Criar uma taxonomia fixa para fatos, preferências, projetos, pessoas, decisões, missões, descobertas, Skills, incidentes e resultados. Cada registro deverá possuir origem, confiança, data, escopo e possibilidade de correção.

Implementar busca por projeto, prioridade e recência. Criar resumos compactos por projeto. Separar memória global da memória de cada projeto. Impedir que um projeto injete dados de outro sem autorização.

Manter o Obsidian como espelho legível, com índices de fatos, decisões, missões, Skills, pesquisas e chat do Lab. A sincronização deverá ser best-effort e nunca poderá quebrar a memória interna.

**Pronto quando:** a ZARA conseguir responder “o que é este projeto?”, “qual foi a última decisão?” e “qual tarefa está pendente?” usando registros reais e citando a origem.

## Fase 4 — Controle seguro do Windows

**Objetivo:** ampliar o controle local por níveis de risco.

Evoluir o controle em camadas. A primeira camada será abrir, fechar, focar, consultar janelas e ler estado. A segunda incluirá teclado, mouse, clipboard, arquivos e pastas. A terceira incluirá navegador, formulários e mídia. A quarta incluirá serviços, rede, energia e manutenção do sistema.

Cada ação deverá declarar risco, escopo, pré-condição, pós-condição, possibilidade de desfazer e necessidade de confirmação. Operações destrutivas deverão exigir confirmação imediata e mostrar o alvo exato.

Adicionar modo de simulação. Antes de mover, renomear ou apagar, a ZARA deverá mostrar o plano e produzir uma prévia. Para exclusões, preferir lixeira ou quarentena, nunca apagar diretamente por padrão.

**Pronto quando:** cada ação suportada tiver verificador automático, teste reversível e registro completo.

## Fase 5 — Visão de tela e interação multimodal

**Objetivo:** permitir que a ZARA entenda a interface sem fingir que viu algo que não viu.

Criar captura autorizada da tela, OCR, identificação de janelas, localização de texto e identificação de controles. Cada leitura deverá registrar quando foi feita e em qual janela.

Separar “ler a tela” de “clicar”. A leitura não autoriza a ação. O clique deverá usar um alvo identificado, uma janela correta e uma verificação posterior.

Adicionar um modo de demonstração no qual a ZARA descreve o que pretende clicar sem clicar. Só depois do teste será permitida a execução.

**Pronto quando:** a ZARA localizar um botão em uma aplicação de teste, mostrar o alvo, clicar somente após autorização e confirmar a mudança visual.

## Fase 6 — Voz natural e memória de contexto

**Objetivo:** tornar a interação mais próxima de uma assistente de uso diário.

Implementar wake word configurável, escuta com limites, interrupção de fala, confirmação por voz e fallback para texto. A ZARA deverá reconhecer o projeto ativo, pronomes e referências como “essa pasta”, “o arquivo anterior” e “a tarefa que deixamos ontem”.

A escuta contínua deverá ter indicador visual, botão físico de pausa e registro mínimo. Áudio bruto não deverá ser guardado por padrão. Comandos de alto risco nunca deverão ser autorizados apenas por uma frase ambígua.

**Pronto quando:** uma sequência de três comandos relacionados funcionar sem perder contexto e uma ação perigosa exigir confirmação clara.

## Fase 7 — Pesquisa, aprendizagem e Skills

**Objetivo:** transformar pesquisa em capacidade reutilizável com segurança.

Criar missões de pesquisa com fontes, data, URL, hash, credibilidade e escopo. Separar resumo de evidência. Não tratar um vídeo, post ou página como verdade sem contexto.

O ciclo de Skill deverá ser:

```text
IDEA → DRAFT → TESTING → READY → WAITING_CEO → ACTIVE → RETIRED
```

Cada Skill deverá declarar entradas, saídas, permissões, dependências, limites, testes e rollback. O código descoberto deverá ser isolado, analisado e executado apenas em sandbox. A ativação deverá apontar para uma versão conhecida.

**Pronto quando:** a ZARA criar uma Skill candidata de leitura, testá-la sem acesso destrutivo, apresentar evidências e retornar à versão anterior após rollback.

## Fase 8 — ZARA Lab como empresa de agentes

**Objetivo:** transformar o chat do Lab em uma fila de trabalho organizada.

Definir papéis com limites claros. Pesquisadores coletam evidências. Arquitetos transformam evidências em planos. Engenheiros definem contratos. Codadores alteram apenas a sandbox. Testadores tentam quebrar a mudança. Revisores verificam o diff. O CEO aprova ou rejeita.

Cada missão deverá ter dono, prazo, escopo, orçamento, dependências, artefatos, critérios de pronto e motivo de encerramento. Handoffs deverão usar mensagens estruturadas e links para evidências, não apenas texto livre.

Adicionar reuniões automáticas curtas do Lab: triagem, planejamento, revisão de risco e relatório diário. O sistema não deverá criar trabalho infinito só para manter agentes ocupados.

**Pronto quando:** uma missão passar por todos os papéis e gerar um pacote de decisão que uma pessoa não técnica consiga entender.

## Fase 9 — Engenharia de software autônoma governada

**Objetivo:** permitir que o Lab melhore o próprio código sem quebrar a ZARA.

O pipeline deverá criar snapshot, executar baseline, produzir patch limitado, rodar testes, fazer revisão independente, empacotar candidato, executar canário e aguardar aprovação. O build ativo nunca será alterado durante a experimentação.

Adicionar análise de dependências, detecção de arquivos órfãos, verificação de imports, testes de IPC, teste de contrato entre frontend e backend e relatório de cobertura das áreas críticas.

Criar uma matriz de risco para alterações. Interface visual terá risco menor que executor de arquivos. Memória terá risco de privacidade. Controle do Windows terá risco operacional. Segurança e autenticação terão revisão obrigatória.

**Pronto quando:** nenhuma proposta conseguir chegar ao build ativo sem passar pelos gates definidos no plano seguro.

## Fase 10 — Providers, Nine Router e custos

**Objetivo:** tornar a escolha de modelo verificável e eficiente.

Separar registro de provider, autenticação, teste de conectividade, quota, latência e qualidade. Criar health checks reais no Windows e um painel que mostre qual modelo respondeu, quando respondeu e se falhou.

Adicionar roteamento por tipo de tarefa: resposta rápida, planejamento, visão, código, voz, resumo e revisão. Implementar fallback explícito, limite de custo, retry curto e circuit breaker.

Nenhum provider será declarado funcionando apenas porque aparece na configuração. A prova deverá incluir autenticação, chamada real, resposta válida e comportamento no pacote instalado.

**Pronto quando:** o usuário puder ver por que um modelo foi escolhido e o sistema puder continuar com segurança quando um provider estiver indisponível.

## Fase 11 — Navegador, agenda e integrações

**Objetivo:** permitir que a ZARA trabalhe em serviços externos sem perder controle.

Adicionar browser session controlada, navegação com domínio permitido, leitura de páginas, preenchimento de formulários, downloads para quarentena e confirmação antes de enviar ou publicar algo.

Criar conectores para agenda, arquivos e comunicação somente quando houver autenticação clara, escopo mínimo e botão de desconectar. Tokens deverão ficar fora do repositório e nunca aparecer na memória do Lab.

**Pronto quando:** uma tarefa de pesquisa e anotação funcionar com logs, fonte, confirmação e revogação de acesso.

## Fase 12 — Resiliência e operação no Windows

**Objetivo:** fazer a ZARA voltar de falhas sem criar processos órfãos.

Criar health checks para Electron, preload, IPC, sidecar, banco, Obsidian, provider e scheduler. Registrar heartbeat e estado de inicialização. Recuperar operações duráveis após reinício.

Avaliar um modo opcional de inicialização com o Windows. Esse modo deverá ser visível, desativável, documentado e limitado ao processo oficial da ZARA. Um serviço externo só deverá ser criado depois de uma decisão explícita de produto.

Adicionar testes para queda do backend, perda do vault, rede indisponível, provider fora do ar, volume desconectado e atualização interrompida.

**Pronto quando:** a ZARA reiniciar, detectar o que ficou pendente, não repetir ações idempotentes e apresentar um relatório claro.

## Fase 13 — Segurança e privacidade

**Objetivo:** tornar segurança uma capacidade permanente.

Criar permissões por ferramenta, projeto, agente e usuário. Adicionar allowlist de diretórios, bloqueio de symlink, proteção contra prompt injection, redaction de segredos e auditoria de leitura e escrita.

Criar um centro de permissões com três estados: permitido, pedir confirmação e bloqueado. O usuário deverá conseguir revogar um conector, pausar o Autopilot e apagar uma memória específica.

Executar testes adversariais internos: comandos ambíguos, páginas maliciosas, arquivos com instruções falsas, nomes enganadores e tentativas de escapar do sandbox.

**Pronto quando:** o sistema bloquear uma tentativa de ultrapassar escopo e mostrar exatamente qual regra foi aplicada.

## Fase 14 — Experiência de produto

**Objetivo:** esconder a complexidade sem esconder o controle.

Criar uma tela inicial simples com: o que a ZARA está fazendo, o que terminou, o que precisa de aprovação, o que está bloqueado e como desfazer.

O Lab deverá ter três visões: conversa, missões e decisões. A pessoa não técnica não deverá precisar ler logs para entender o resultado. Cada ação deverá ter uma explicação curta e um botão para ver detalhes.

Adicionar notificações úteis, histórico pesquisável, filtros por projeto e um modo de demonstração para novos recursos.

**Pronto quando:** o usuário conseguir abrir o Lab e responder em menos de um minuto: “o que está acontecendo, o que precisa de mim e o que pode dar errado?”.

## Fase 15 — Teste físico e release

**Objetivo:** transformar código validado em produto instalável.

O build final deverá ser feito em candidato separado. Os cinco artefatos obrigatórios deverão ser verificados. O instalador deverá ser aberto no Windows. O teste deverá confirmar startup, tray, preload, IPC, sidecar, memória, texto, uma ação reversível e rollback.

Depois serão testados voz, microfone, navegador, provider, Nine Router e início automático. Cada resultado será classificado como `SOURCE`, `TEST`, `RUNTIME_AUTOMATED`, `PACKAGED_RUNTIME`, `PHYSICAL_BY_ALEX` ou `VOICE_PHYSICAL`.

**Pronto quando:** o mesmo pacote testado for o pacote aprovado e o conhecido-bom estiver preservado para rollback.

## Como o Lab trabalhará a partir de agora

O Lab deverá criar missões pequenas e independentes. Cada missão deverá declarar objetivo, arquivos permitidos, testes obrigatórios e condição de parada. O supervisor não deverá iniciar uma nova missão quando existir uma falha sem triagem.

A rotina recomendada é:

1. Triar problemas e oportunidades.
2. Escolher no máximo três missões prioritárias.
3. Pesquisar e registrar evidências.
4. Criar plano limitado.
5. Implementar em sandbox.
6. Rodar baseline e testes do candidato.
7. Fazer revisão independente.
8. Gerar relatório para o CEO.
9. Aprovar, rejeitar ou pedir ajustes.
10. Empacotar e testar no Windows.

## Prioridades práticas

A ordem mais inteligente é estabilizar a base antes de adicionar dezenas de funções. A prioridade imediata é: organização da raiz, contratos de estado, saúde do runtime, memória real, teste físico do Windows, controle básico reversível, ciclo de Skills e pipeline do Lab. Depois vêm visão, voz, navegador, integrações e maior autonomia.

Não é inteligente começar por controle total do disco, limpeza automática, instalação irrestrita de código ou 313 agentes trabalhando sem orçamento. Isso aumentaria o risco e dificultaria saber qual mudança causou um problema.

## Métricas para medir a evolução

A ZARA será considerada melhor quando os números melhorarem de forma comprovável:

| Métrica | Medição |
|---|---|
| Taxa de conclusão | Tarefas concluídas com verificação divididas por tarefas iniciadas |
| Taxa de erro | Ações que falharam ou exigiram correção |
| Taxa de rollback | Ativações revertidas após o canário ou uso real |
| Tempo de resposta | Tempo entre pedido e plano, e entre plano e resultado |
| Memória útil | Perguntas respondidas com fonte correta e projeto correto |
| Recuperação | Operações retomadas sem duplicação após reinício |
| Segurança | Tentativas de escopo indevido bloqueadas corretamente |
| Eficiência | Custo e quantidade de chamadas por tarefa concluída |
| Cobertura física | Recursos testados no Windows empacotado |

## Primeiro ciclo de implementação

O primeiro ciclo deverá executar apenas estas entregas:

1. Finalizar o inventário da raiz e o índice da quarentena.
2. Consolidar o contrato de estado entre backend, IPC e frontend.
3. Criar painel de saúde do Autopilot e do Lab.
4. Criar teste real de conexão e gravação no Obsidian configurado.
5. Criar um teste reversível de abrir, focar e fechar o Bloco de Notas.
6. Melhorar o relatório de candidatos e rollback.
7. Criar o relatório diário do Lab.
8. Preparar o checklist do build físico no Windows.

Depois desse ciclo, será possível começar visão, voz e navegador com uma base muito mais confiável.

## Critério de sucesso do programa

A ZARA estará próxima do objetivo quando conseguir receber uma ordem em linguagem natural, identificar o projeto correto, explicar seu plano, executar uma tarefa de baixo risco, pedir autorização para a parte sensível, verificar o resultado, registrar a decisão no segundo cérebro, criar uma proposta de melhoria e recuperar-se de uma falha sem perder o estado.

Esse é o caminho concreto para aproximá-la de uma assistente de sistema real. A aparência de JARVIS virá da combinação entre voz, contexto, visão e automação. A confiabilidade virá dos gates, dos testes, da memória correta e do rollback.

## Referências

[1]: docs/PLANO_EXECUCAO_AUTOPILOT_SEGURO.md "Plano de execução seguro da ZARA Autopilot"

[2]: docs/ARQUITETURA_AUTOPILOT_TOTAL.md "Arquitetura total do Autopilot"

[3]: docs/ZARA_DOCUMENTACAO_UNICA.md "Documentação única da ZARA"

[4]: docs/AUTOPILOT_BUILD_E_TESTE.md "Build e teste do Autopilot"
