# Auditoria funcional do aplicativo empacotado — 2026-08-08

## Escopo e segurança

- Aplicativo exercitado: `frontend/release/win-unpacked/ZARA 3.0.exe`.
- Perfil de teste isolado: `%TEMP%/zara-exe-capability-test-20260808`.
- Nenhum arquivo pessoal foi alterado.
- A rodada sem modelos externos limpou as chaves do ambiente do processo antes da abertura.
- Ações que gravam arquivos foram tentadas somente contra um arquivo descartável dentro do perfil isolado.
- Microfone, captura de tela, OCR, alterações físicas no computador e ações HIGH não foram executados.
- O pacote testado foi gerado antes da promoção do Realtime Web Core. O backend dentro do pacote tem SHA-256
  `639E4D80FA54C2A50F77EF161D1C0C49AF5CD7FF24638401BD44EAEF9B18BBCC`; o sidecar atual em
  `dist-sidecar` tem SHA-256 `C54E76656A6DAAFCE4421D926A294A3655EE0D6F56F76655FA71704096DFC1AC`.

## Resultado por capacidade

| Capacidade | Resultado no `.exe` | Evidência observada |
|---|---|---|
| Abertura do app | PASS | Janela, renderer e backend ficaram ONLINE. |
| Interface principal | PASS | Home, seletor de motor, métricas, Lab e modais renderizaram sem erro de página. |
| Diagnóstico do sistema | PASS | CPU, RAM, plataforma, processador e versão do Python foram consultados. |
| Seleção de motor | PASS parcial | Alternância `AUTO INTELIGENTE` / `AUTO ECONÔMICO` confirmada. Sem chaves, somente os modos automáticos são listados. |
| Chat sem serviço externo | PASS seguro | Retornou honestamente que nenhum motor R$0 compatível estava disponível; não fez chamada paga. |
| Chat externo real | NÃO TESTADO | Evitado porque não há prova local de que o projeto associado à chave esteja no tier gratuito. |
| Conversation Log | FAIL parcial | A conversa aparece na sessão, mas a tela volta vazia após reiniciar. |
| Episódios de memória | PASS parcial | O turno de chat foi gravado em SQLite; não há recuperação integrada comprovada. |
| Memory Galaxy | PLACEHOLDER | Abre, porém declara que aguarda integração real e usa nós demonstrativos. |
| ZARA Lab — conversa | PASS | ZARA respondeu no Council Room. |
| ZARA Lab — proposta | PASS | Proposta LOW foi criada e aprovada no perfil isolado. |
| ZARA Lab — fila | PASS parcial | Aprovação criou uma tarefa persistente; ela permaneceu QUEUED porque não existe worker executor. |
| Persistência do Lab | PASS | Proposta e tarefa reapareceram depois de fechar e abrir o app. |
| Acentuação do Lab | FAIL | Texto digitado com acentos reapareceu com mojibake, por exemplo `validaÃ§Ã£o`. |
| Lembrete por linguagem natural | PASS parcial | O lembrete foi criado localmente e o banco mudou de SCHEDULED para FIRED no horário. |
| Entrega do lembrete | FAIL | Nenhum aviso apareceu na interface quando o horário chegou. |
| Resposta de criação do lembrete | FAIL | A confirmação apareceu duas vezes e com texto/acentos corrompidos. |
| Busca simples na web | PASS | `web_search` retornou duas fontes oficiais em menos de um segundo, sem chave paga. |
| Leitura protegida de página | PASS | `web_fetch` leu `docs.python.org` com limite de 8 KiB e marcou truncamento. |
| Realtime Web com citações | NÃO CERTIFICADO NO PACOTE | A versão nova funciona em source, mas o sidecar novo congelado ainda atinge o limite de tempo. |
| Leitura de arquivos | PASS | Listagem de uma pasta isolada funcionou. |
| Análise de código | PASS | `main.py` foi analisado e suas funções/imports foram retornados. |
| Bloqueio de escrita | PASS de segurança | `files_write` foi negado com Supercérebro OFF e nenhum arquivo foi criado. |
| Catálogo de ações | PASS | 43 ações registradas: 22 LOW, 15 MEDIUM e 6 HIGH. |
| Acesso natural às ações | FAIL | O chat comum não possui loop de ferramentas; as ações existem internamente, mas não são chamadas naturalmente. |
| Scheduler | PASS somente leitura | A lista foi consultada e estava vazia; o executor do scheduler não está inicializado. |
| Supercérebro fail-closed | PASS parcial | A interface permaneceu OFF quando a ativação não foi confirmada. |
| Ciclo de vida do Hermes | FAIL | A tentativa iniciou um gateway Hermes que continuou após o app fechar, embora a interface mostrasse OFF. O processo de teste foi encerrado manualmente. |
| Encerramento do backend | FAIL | Fechar o Electron matou apenas o processo-pai do sidecar onefile e deixou o processo Python real órfão. O órfão de teste foi encerrado manualmente. |

## Ações internas encontradas

O pacote expõe 43 ações nas categorias navegador, código, arquivos, sistema operacional, scheduler, sistema,
visão e web. Elas formam uma base útil, mas não significam que Alex consiga usá-las pela conversa atual.
O Capability Gate bloqueou corretamente uma escrita de arquivo com o Supercérebro desligado.

## Testes deliberadamente pendentes

1. Microfone, wake word, STT, TTS e interrupção de voz — exigem autorização para captar áudio do ambiente.
2. Resposta de um modelo externo — exige comprovar que a chave pertence a um projeto sem cobrança.
3. Screenshot/OCR — captura potencialmente conteúdo privado da tela.
4. Controle físico do PC e ações HIGH — exigem uma matriz de casos isolados e confirmação humana.
5. Instalador — esta rodada usou o executável `win-unpacked`, sem instalar ou alterar o Windows.
6. Realtime Web novo no Electron — depende da correção do sidecar congelado e de novo pacote.

## Prioridade técnica resultante

1. Corrigir encerramento de toda a árvore do sidecar e do gateway Hermes.
2. Corrigir lembretes ponta a ponta: callback, evento Electron, duplicação e UTF-8.
3. Concluir o Realtime Web no sidecar congelado e reempacotar.
4. Persistir e recuperar conversas/memórias na interface.
5. Ligar o chat ao Capability Gate e às ações registradas.
6. Executar a rodada de voz/hardware com autorização de Alex.

## Limpeza

Os processos órfãos criados pela rodada foram identificados pelo caminho e PID exatos e encerrados. Nenhum
gateway Hermes ou sidecar do pacote testado permaneceu em execução ao término da auditoria. O perfil isolado
foi preservado temporariamente como evidência até a conclusão das correções.
