# ZARA — viabilidade oficial de IA e voz

Pesquisa em 6 de setembro de 2026. Este documento responde às seções 28–37 da direção de produto enviada por Alex. É uma avaliação de integração: não afirma que o novo adaptador foi implementado ou que uma sessão paga foi testada. Nenhuma credencial foi lida e nenhuma chamada de inferência foi feita nesta pesquisa.

## Decisão

**ZARA pode continuar sendo a interface e usar Codex como um dos seus agentes, aproveitando a autenticação ChatGPT da pessoa.** Há interfaces oficiais para isso. A melhor base para uma integração profunda é o Codex App Server; a ponte CLI existente continua sendo um ponto de partida útil. **Não encontrei uma interface pública documentada que permita incorporar o áudio do ChatGPT Voice incluído no Plus diretamente no Electron ZARA.** Para voz própria, a alternativa OpenAI documentada é a Realtime API, com cobrança própria.

As conclusões abaixo distinguem uma capacidade oficial do fornecedor, uma implementação encontrada no repositório e uma proposta que ainda precisa ser construída. Não significam promessa de acesso à conta, disponibilidade de qualquer modelo específico ou funcionamento sem limites.

## Plus, API e Codex

| Pergunta | Resposta verificada |
|---|---|
| Codex está incluído no Plus? | Sim. A documentação de planos inclui o Plus e descreve limites compartilhados entre Codex e ChatGPT Work. O volume depende do modelo e do trabalho; não é uma franquia ilimitada. [Planos e uso](https://learn.chatgpt.com/docs/pricing). |
| Posso usar a assinatura no Codex local? | Sim. O login ChatGPT é documentado como acesso por assinatura; login com chave API usa cobrança por consumo. O CLI aceita o fluxo oficial de login no navegador. [Autenticação](https://learn.chatgpt.com/docs/auth). |
| Posso enviar uma tarefa por programa? | Sim. `codex exec` recebe tarefas, pode emitir JSONL, retoma sessões por ID e reutiliza a autenticação CLI salva por padrão. [Modo não interativo](https://learn.chatgpt.com/docs/non-interactive-mode). |
| Plus é uma chave gratuita para qualquer endpoint de modelo? | Não há esse contrato nas interfaces consultadas. O acesso por assinatura descrito aqui pertence ao Codex; a API geral tem autenticação própria. [Autenticação API](https://platform.openai.com/docs/api-reference/introduction), [autenticação Codex](https://learn.chatgpt.com/docs/auth). |
| A ZARA pode ser um cliente próprio? | Sim. A documentação apresenta o App Server especificamente para incorporar Codex a produtos próprios. [App Server](https://learn.chatgpt.com/docs/app-server). |

**Implicação para Alex:** tarefas locais enviadas ao Codex autenticado com sua conta podem usar a franquia correspondente, em vez de uma chave API. Isso consome a mesma capacidade disponível para seu trabalho no Codex. O aplicativo deve mostrar qual modalidade está ativa. Não deve alternar silenciosamente para cobrança API quando a franquia acabar. Para CI compartilhado e automação de serviço, a documentação orienta autenticação própria adequada ao ambiente; não tratar uma conta pessoal como credencial de servidor público. [Autenticação](https://learn.chatgpt.com/docs/auth), [planos e uso](https://learn.chatgpt.com/docs/pricing).

## Integração oficial mantendo a face ZARA

O App Server oferece autenticação, histórico, aprovações e eventos de execução. O transporte padrão é `stdio`, com mensagens JSONL em protocolo bidirecional baseado em JSON-RPC. Há operações para iniciar/retomar threads, executar/interromper turnos, consultar modelos e limites. O OAuth gerenciado deixa login, armazenamento e renovação de credenciais com Codex. A documentação marca o transporte TCP WebSocket e ferramentas dinâmicas como experimentais; a integração inicial deve usar `stdio` e ferramentas MCP. [Contrato do App Server](https://learn.chatgpt.com/docs/app-server).

O SDK TypeScript oficial permite iniciar, continuar e retomar threads locais e roda no lado servidor com Node.js 18+. Também existe SDK Python oficial estável, baseado no App Server, para Python 3.10+, com runtime fixado nas distribuições publicadas. São opções de implementação; não são assinaturas adicionais de modelo. [Codex SDK](https://learn.chatgpt.com/docs/codex-sdk).

Proposta para a ZARA:

```text
ZARA Electron — interface, voz, presença e controles
    ↓ IPC restrito
ZARA Agent Gateway — identidade da tarefa, estado e orçamento
    ↓ adaptador local de Codex
Codex App Server — login ChatGPT gerenciado e sessão persistente
    ↕ MCP local com ferramentas explicitamente expostas
ZARA Executor — autorização, execução, verificação e resultado
```

O diagrama é uma decisão de arquitetura para implementação futura. O adaptador deve manter `task_id`, `thread_id`, `turn_id`, eventos e resultados correlacionados; um cancelamento deve chegar ao trabalho real. A ZARA mantém seu histórico de produto e referências da sessão externa, sem duplicar toda memória a cada turno. A lista de ferramentas expostas deve preservar as restrições do executor existente. O texto do modelo não é prova de que uma alteração ocorreu: o executor registra o resultado observado.

A escolha de modelo e esforço precisa consultar disponibilidade real e considerar a tarefa. Codex é um agente generalista com ferramentas, não um substituto obrigatório para cada consulta rápida, reconhecimento de voz ou ação determinística. Na primeira versão, uma tarefa usa um agente executor; revisão adicional só entra quando risco ou incerteza justificam.

## MCP, plugins e a arquitetura inversa

MCP fornece ferramentas e contexto ao modelo. Clientes Codex locais suportam servidores STDIO e Streamable HTTP. No ChatGPT web, ferramentas remotas chegam por plugins; o site não lê a configuração MCP local do computador. [MCP no ChatGPT e Codex](https://learn.chatgpt.com/docs/extend/mcp).

O caminho `ChatGPT → plugin/MCP → ferramentas ZARA` é viável como extensão dos clientes OpenAI. A documentação atual redireciona a entrada de Apps SDK para plugins, que agregam habilidades e conexões com serviços. Essa extensão coloca a experiência principal no cliente ChatGPT/Codex; não entrega, por si só, uma API de conversa Plus para o Electron. [Plugins](https://developers.openai.com/plugins).

Minha recomendação é oferecer esse caminho como integração complementar. Ele permitiria solicitar uma operação ZARA de dentro do ambiente OpenAI. Para preservar a experiência ZARA como produto principal, usar o cliente próprio descrito acima. Ambos podem compartilhar uma implementação de ferramentas com contratos e permissões iguais.

Não confundir duas direções: **Codex consumir ferramentas MCP da ZARA** continua sendo documentado; **executar Codex como servidor via `codex mcp-server`** está depreciado. Para nova integração, a própria documentação indica App Server. [Guia de migração do servidor MCP](https://learn.chatgpt.com/docs/mcp-server).

## Voz: o que é suportado

ChatGPT Voice é documentado em Chat, Work e Codex no aplicativo desktop ChatGPT, com disponibilidade dependente de plano e rollout. Permite conversa, interrupção, acompanhamento e delegação de tarefas. Essa documentação descreve o uso no produto OpenAI e não fornece um SDK de incorporação da voz Plus em uma aplicação Electron externa. Portanto, a promessa **“a mesma voz do Plus embutida na ZARA e coberta pela mensalidade” permanece sem suporte público estabelecido**. Essa é uma conclusão sobre a documentação consultada, não a alegação de que tal recurso nunca poderá existir. [ChatGPT Voice](https://learn.chatgpt.com/docs/features/voice).

Para uma aplicação própria, Realtime oferece áudio em tempo real e ferramentas. WebRTC é o caminho recomendado para clientes que capturam e reproduzem áudio; WebSocket é adequado a pipelines de áudio no servidor. [Realtime e áudio](https://developers.openai.com/api/docs/guides/realtime).

A conexão WebRTC pode usar uma credencial efêmera emitida pelo backend, autenticado com chave API. A chave duradoura não deve chegar ao renderer. Isso é autenticação da API, não exportação do login Plus. [WebRTC oficial](https://developers.openai.com/api/docs/guides/realtime-webrtc). O VAD pode cancelar a resposta quando a pessoa interrompe; reprodução e histórico precisam refletir o trecho realmente ouvido. [Interrupções e conversas](https://developers.openai.com/api/docs/guides/realtime-conversations).

O custo das sessões de agente de voz é calculado por tokens de entrada e saída, incluindo áudio e contexto; transcrição e tradução por streaming têm regras próprias. Sessões longas exigem controle de contexto e orçamento. Não há número universal de “reais por minuto” nem latência garantida por esta pesquisa. [Custos Realtime](https://developers.openai.com/api/docs/guides/realtime-costs).

| Caminho | Voz, interrupção e ferramentas | Custo e avaliação |
|---|---|---|
| ChatGPT Plus Voice | Experiência no cliente OpenAI; conversa e interrupção documentadas. Incorporação externa do áudio não estabelecida. | Franquia do plano; tarefas e voz têm contabilidade própria. [Uso de Voice](https://learn.chatgpt.com/docs/pricing). |
| OpenAI Realtime | Áudio nativo, transcrições opcionais, eventos e chamadas de ferramentas; exige integração de sessão e cancelamento. | API por consumo. Naturalidade e latência devem ser avaliadas em português brasileiro no dispositivo. [Realtime](https://developers.openai.com/api/docs/guides/realtime). |
| ZARA atual — Gemini/Kore | Caminho de áudio já implementado; geração direta em alguns turnos e retorno via executor em outros. Possui eventos de interrupção e transporte Electron com AEC. | Depende do provedor/configuração. A existência do código não comprova quota, qualidade ou latência desta instalação. |
| ZARA atual — local/fallback | Vosk para STT; cascata de TTS com Edge, Kokoro e Gemini HTTP quando disponíveis. Interrupção varia pelo caminho. | Modelos locais exigem arquivos e computação. Edge é dependência externa; não há SLA ou franquia garantida verificados aqui. |
| Híbrido proposto | Voz existente ou Realtime recebe a fala; tarefas longas seguem para Codex; executor ZARA devolve evidência e a voz apresenta o resultado. | Soma os custos efetivamente usados. Delegar uma tarefa de voz ao Codex não torna o áudio da API coberto pelo Plus. |

As duas primeiras linhas se apoiam nas fontes oficiais citadas. As duas linhas da ZARA descrevem inspeção de código, sem benchmark. A última é uma proposta. Não há classificação numérica de naturalidade, STT ou latência porque não foi feito teste comparativo de áudio.

## O que existe no repositório

Inspeção do checkout em `7e3624c44cdbce5a4f1114229884cc7deb41d346`, com alterações concorrentes em andamento. Os nomes abaixo descrevem os arquivos lidos, não certificam o executável instalado.

- `core/ponte_codex_cli.py`: já chama `codex exec`/`exec resume`, envia entrada por stdin, lê JSONL e resposta final, salva o ID da conversa e limita tempo. O padrão é somente leitura; há parâmetro explícito para escrita. `core/ipc_handlers.py` usa essa ponte em roteamento para Codex no canal de comunicação. Portanto, Codex não está totalmente ausente do projeto, embora isso ainda não seja o novo Agent Gateway do Lab.
- `core/model_router.py`: registro e saúde de provedores Groq, NVIDIA, Gemini, ZAI, XAI e Ollama. Os modos automáticos existentes têm elegibilidade de custo/quota. Não encontrei um provedor OpenAI Realtime nesse roteador.
- `core/ipc_handlers.py` e `core/gemini_live_voice.py`: caminho efetivamente ligado ao IPC da Home. Começa Gemini Live quando configurado e cai para pipeline Vosk local quando necessário. A configuração do IPC usa transporte `renderer` por padrão, com alternativa local explícita.
- `frontend/src/renderer/lib/aecAudio.ts` e `components/zara-home/VoiceDock.tsx`: captura/reprodução no Electron, solicitação de cancelamento de eco, parada de captura e corte de reprodução. Isso fornece estrutura; a efetividade acústica exige teste físico.
- `core/voice_tts.py` e `_speak_response` em `core/ipc_handlers.py`: preferência por Kore ativa, seguida por Edge Neural, Kokoro e Gemini HTTP conforme disponibilidade. Existe helper SAPI legado, mas ele foi retirado da cascata observada; não apresentar SAPI como a voz atual.
- `voice/local_engine.py` e `voice/voice_manager.py`: há uma arquitetura alternativa com referências a faster-whisper, Kokoro/Piper e Pipecat; contém inclusive tokenização marcada como placeholder. Não encontrei uso desse gerenciador no caminho `main.py → core/ipc_handlers.py` inspecionado. Não afirmar que todos esses motores estão prontos no produto.

## Próxima implementação recomendada

1. **Consolidar uma ponte oficial de tarefas:** adaptar a ponte CLI existente para o contrato do Lab e, quando forem necessários login integrado, aprovações e eventos ricos, introduzir App Server via STDIO. Fixar versão e gerar tipos do protocolo usados na implementação.
2. **Manter uma identidade e um executor:** memória, permissões e verificação continuam pertencendo à ZARA. Registrar origem de cada resultado e o estado real de cada agente. Não mostrar “conectado” apenas porque um binário existe.
3. **Tratar voz como subsistema independente:** melhorar e medir o caminho existente; oferecer Realtime como opção explícita com configuração e orçamento próprios. Não rebatizar Kore como ChatGPT Voice.
4. **Validar antes de promover:** login/cota, retomada após reinício, cancelamento, aprovação, falha de ferramenta, indisponibilidade de rede, duas tarefas simultâneas e recuperação de processo. Para áudio: amostra em português brasileiro, ruído, distância, interrupção humana, eco, fim de frase e p50/p95 até o primeiro áudio útil.

Critério de produto: ZARA deve responder rapidamente ao que é simples, encaminhar trabalho longo com estado visível e falar apenas o que pode sustentar. A arquitetura híbrida oferece esse caminho sem depender de scraping, cookies, endpoints privados ou automação de tela para simular uma API.
