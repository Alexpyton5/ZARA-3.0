# Proposta técnica — raciocínio livre no intent de PC da ZARA

Data: 2026-08-28
Autor: subagente de pesquisa (Claude Code), sob pedido do Alex via CEO_MENTOR
Status: PROPOSTA — nenhum arquivo de código foi alterado para produzir este documento
Arquivos lidos por inteiro para esta proposta: `core/pc_voice_intent.py` (975 linhas),
`core/zara_orchestrator.py` (463 linhas); trechos lidos de `core/ipc_handlers.py`
(cadeia de dispatch, guarda `_looks_like_unhandled_local_action`, `_try_pc_intent`) e
de `core/model_router.py` (catálogo de modelos e providers).

---

## (a) O problema real, baseado no que foi lido

### Como funciona hoje

`PcVoiceIntentDetector.detect()` (`core/pc_voice_intent.py`) é uma lista fixa de
pouco mais de 90 tuplas `(regex, handler, action, default_param)`, percorrida em
ORDEM com `re.search` na primeira que casar — mais alguns blocos de `re.fullmatch`
tratados antes do laço para casos contextuais ("mais alto", "minimize ele").
Cada regex mapeia para uma ação já existente em `core/action_registry.py`. Isso é
determinístico, rápido (regex compilado sobre string curta, sem I/O, sem rede) e
fácil de auditar — é também exatamente o que dá à ZARA a garantia do projeto de
que reflexo local não depende do Supercérebro (`_blocked_by_superbrain`,
`_LOCAL_DETERMINISTIC_ACTIONS`).

O preço dessa arquitetura é rigidez: só é reconhecido o que está escrito num
regex. Fora disso, a cadeia de dispatch em `ipc_handlers.py`
(`_try_compound_pc_intent` → `_try_pc_intent` → `_looks_like_unhandled_local_action`)
tem **dois destinos diferentes para frases que o regex não cobre**, e os dois são
ruins de um jeito diferente:

1. **A frase começa com um verbo de ação que o guarda reconhece**
   (`_looks_like_unhandled_local_action`, ancorado em `^\s*(abra|feche|aumente|
   diminua|...)`), mas nenhum regex específico bateu. Resultado: recusa honesta
   fixa (`RESPOSTA_NAO_SEI`, "Isso eu ainda não sei fazer..."). Seguro — nunca
   finge que executou — mas é literalmente o "jeito fixo" que o Alex reclamou:
   só entende o comando dentro do vocabulário e da ordem de palavras que alguém
   já pensou em escrever como regex.

2. **A frase pede a mesma coisa de um jeito indireto, educado ou reformulado que
   não começa com um dos verbos do guarda** (ex.: "será que dava pra abaixar um
   pouco esse som", "não tá um pouco escuro esse brilho?", "quero a tela mais
   apagada"). Isso **escapa dos dois filtros** — não bate no regex, não bate no
   guarda porque o guarda só olha o início da frase — e cai direto em
   `self.orchestrator.process_message(text, ...)`, que chama
   `zara_orchestrator.py`.

O ponto 2 é o achado mais importante desta leitura: **`ZaraOrchestrator.process_message`
não tem nenhuma noção de ação de PC.** Os quatro métodos de chamada de modelo
(`_call_hermes`, `_call_ollama`, `_call_openai_compatible`, `_call_gemini`) montam
só `{system_prompt, histórico, mensagem}` e devolvem texto livre — não há `tools`,
`function_call` nem qualquer schema de saída estruturada no payload, em nenhum dos
quatro. Ou seja: quando uma frase de controle de PC escapa do regex e do guarda,
ela vira uma pergunta de conversa comum para um modelo que não sabe que existe um
`ActionRegistry`, não tem como executar `os_brightness_down` e pode responder
numa forma que **soa** como confirmação de ação sem nenhum executor ter rodado.
É exatamente o risco que `evidence.md` já nomeia ("resposta de modelo nunca é
prova de ação") — aqui ele não é hipotético, é um buraco estrutural concreto na
cadeia atual, alcançável por qualquer frase de controle que não comece com um
verbo do guarda.

`core/action_registry.py` já expõe a lista fechada de ações reais
(`ActionRegistry._specs` / `get_all_specs()`), com nome e (via `ActionSpec`)
metadados — essa lista é o inventário correto para qualquer camada de
interpretação escolher a partir dela, nunca para inventar ação nova.

### Resumo em uma frase

Hoje existem só dois modos: "bate no regex certinho" ou "não". Não existe modo
intermediário de "entendi o que você quis dizer, mesmo falando diferente,
dentre as coisas que eu sei fazer". Construir esse modo intermediário sem
tornar cada comando de PC dependente de uma chamada de rede é o problema real.

---

## (b) Abordagens técnicas

### Abordagem 1 — trocar o roteador por IA sempre

Toda frase (ou toda frase que "parece" comando de PC) passa primeiro por uma
chamada de modelo que decide a ação, antes ou no lugar do regex.

**Prós**
- Resolve o "jeito fixo" de forma completa e uniforme — qualquer forma de falar
  tem chance de ser entendida, não só as reformulações previstas.
- Um só caminho de código para manter em vez de regex + exceções crescendo.

**Contras**
- Coloca uma chamada de rede em TODO comando doméstico — inclusive os que hoje
  são reflexo local de microssegundos (volume, brilho, wifi, minimizar janela).
  Isso contraria de frente a prioridade #2 que o próprio Alex pediu no mesmo
  dia (latência mínima).
- Vira ponto único de falha: sem rede ou com o provedor de IA fora do ar, nem
  "abra o Chrome" funcionaria mais — pior que hoje.
- Reintroduz o padrão que a Lei Arquitetural do projeto proíbe explicitamente:
  "reflexos locais determinísticos não podem depender do Supercérebro estar
  ligado". Rotear todo comando por um modelo é, na prática, recriar essa
  dependência por outra porta.
- `zara_orchestrator.py` não tem function-calling hoje — seria preciso
  construir do zero o schema de saída, o parsing e a validação contra o
  `ActionRegistry`, não é "ligar um botão que já existe".
- Mesmo com IA decidindo, ainda seria obrigatório validar a ação escolhida
  contra a lista real (para não inventar ação) — ou seja, nunca elimina a
  necessidade de uma camada de guarda.

### Abordagem 2 — regex determinístico expandido (sem IA)

Aumentar a cobertura do detector atual com mais sinônimos, mais formas
coloquiais, normalização morfológica leve e/ou correspondência aproximada de
string (ex.: `rapidfuzz`) contra os padrões conhecidos.

**Prós**
- Zero latência nova, zero rede, zero custo — mantém a garantia de reflexo
  local sem Supercérebro intacta.
- Simples de testar e de reverter: cada entrada nova é isolada, sem mudança de
  arquitetura.

**Contras**
- Não resolve o problema que o Alex descreveu. Ele não pediu "mais um
  sinônimo na lista", pediu para não precisar decorar nenhum jeito de falar.
  Frases indiretas, compostas ou com intenção implícita continuam fora do
  alcance de qualquer regex, não importa quantos sinônimos se adicionem.
- É uma correção paliativa que precisa ser repetida a cada nova frase que o
  Alex reportar não funcionar — reproduz o padrão de loop que as regras de
  governança do projeto já identificaram como o problema raiz de sessões
  anteriores.

### Abordagem 3 — híbrida (recomendada)

O regex continua sendo a primeira linha, exatamente como hoje, incluindo o
guarda de recusa honesta. **Só quando a cadeia determinística inteira não
reconhece nada** — nem um padrão específico, nem os intents contextuais —
entra uma segunda camada: um classificador de intenção leve, que recebe a
frase e a lista fechada de ações do `ActionRegistry` (nome + descrição curta
de cada uma) e devolve **ou** um par `(ação existente, parâmetro)` **ou**
"nenhuma das anteriores". Nunca gera código, nunca inventa nome de ação —
é classificação sobre um conjunto fechado, não geração livre de comando.

A saída dessa camada passa pelos MESMOS portões de segurança que a saída do
regex já passa hoje: `res.action not in get_registry()._specs`,
`_blocked_by_superbrain`, a defesa de sintaxe perigosa em parâmetro
(`_SINTAXE_PERIGOSA`), a allowlist de apps. A camada de IA não ganha nenhum
privilégio que o regex não tem — ela só participa de uma etapa antes: decidir
qual ação parece ser, nunca decidir se pode executar.

**Prós**
- Preserva a latência atual no caminho quente: comandos comuns (volume,
  brilho, abrir app, YouTube) continuam batendo no regex e não pagam nenhum
  custo novo.
- O único caminho que fica mais lento é exatamente o caminho que hoje já era
  uma recusa (`RESPOSTA_NAO_SEI`) ou, pior, um silêncio perigoso (cair na
  conversa livre). Ou seja: o pior caso de hoje vira o único caso mais lento
  de amanhã — não o caminho comum.
- Superfície de alucinação pequena porque a escolha é fechada: o modelo não
  escreve uma ação, escolhe um rótulo de uma lista curta e finita, com
  validação de qualquer forma antes de executar.
- Dá para medir o efeito comparando só os casos que caem no fallback — a
  suíte de regex e seus testes não mudam de comportamento.

**Contras**
- Passa a existir dois sistemas de intent para manter em vez de um. Risco
  real: alguém expandir a lista de ações no `ActionRegistry` e esquecer de
  atualizar a lista que o classificador recebe (o mesmo tipo de invariante
  que já existe hoje entre voz e texto — a mitigação é gerar a lista de ações
  permitidas dinamicamente a partir de `get_all_specs()`, nunca copiá-la à
  mão).
- Ainda depende de rede para o fallback. Se a rede cair, o fallback vira "não
  sei" honesto — não piora o estado atual, mas também não é o "sempre
  funciona offline" que os reflexos locais têm hoje.
- Exige desenho cuidadoso do prompt/schema para não devolver uma ação "quase
  certa" com parâmetro errado (ex.: confundir "abaixa o brilho" com "abaixa o
  volume" — dois domínios com verbos parecidos).

**Variante mencionada, não recomendada como primeiro corte:** um estágio
intermediário de similaridade semântica local (embeddings pré-calculados por
ação, sem chamada de rede) entre o regex e a chamada de IA, para reduzir ainda
mais o número de vezes que se paga rede. Tecnicamente viável, mas é uma peça
nova (dependência de embeddings, índice, tuning de limiar) — pela regra do
projeto de não misturar redesenho com uma frente só, isso fica para depois de
a Abordagem 3 básica provar valor, não para o primeiro corte.

---

## (c) Estimativa de latência por abordagem — tudo rotulado INFERIDO

Nada abaixo foi medido fisicamente neste projeto com cronômetro real (a
skill `medir-latencia-da-zara` é o processo correto para isso, comparando a
mesma frase antes/depois no build real). São estimativas por raciocínio sobre
o código lido e sobre ordens de grandeza públicas de latência de API — não
substituem medição.

| Cenário | Estimativa INFERIDA | Base do raciocínio |
|---|---|---|
| Hoje (só regex) | < 5 ms | ~90 regex compilados, `re.search` sobre string curta, sem I/O nem rede; custo de CPU pura em Python é da ordem de dezenas de microssegundos por padrão, mesmo somando todos. |
| Abordagem 1 (IA sempre, todo comando) | ~300–900 ms por comando em condições boas de rede com um modelo rápido (ex. Groq `gpt-oss-20b`); podendo passar de 1,5–2 s com modelos maiores (NVIDIA/Gemini Pro) ou rede ruim | Ordem de grandeza típica de round-trip + inferência de LLM hospedado, por modelos já listados em `core/model_router.py`; nenhuma chamada foi cronometrada neste projeto para esta finalidade. |
| Abordagem 2 (regex expandido) | < 5 ms, igual a hoje | Não introduz chamada nova nem I/O novo. |
| Abordagem 3 (híbrida) — caminho quente (regex bate) | < 5 ms, igual a hoje | Nenhuma mudança no caminho que já funciona. |
| Abordagem 3 — caminho frio (fallback de IA) | mesma faixa da Abordagem 1, ~300–900 ms | É a mesma chamada de modelo, só que restrita aos casos que hoje já eram falha. |

Ponto que não é estimativa, é leitura de código: o custo médio percebido por
Alex na Abordagem 3 depende de **quantos comandos do dia a dia caem no
fallback**. Hoje a maioria dos comandos de uso comum (volume, brilho, abrir
app, YouTube, janelas) já tem regex dedicado — então, supondo que esse padrão
de uso continue, a maior parte das interações não pagaria custo novo. Isso é
inferência sobre o padrão de uso relatado por Alex até aqui, não medição.

---

## (d) Plano de implementação em etapas pequenas, cada uma com rollback

Segue a regra do projeto: uma tarefa, um objetivo, um delta causal. Nenhuma
etapa mistura recuperação com redesenho. Cada etapa é testável isoladamente
antes de a próxima começar.

**Etapa 0 — contrato, sem código.**
Decidir e documentar (sem escrever nada em `core/`) o formato de saída fechado
do classificador: `{"action": <um dos nomes vindos de get_all_specs()>,
"param": <string ou nulo>}` ou `{"action": null}` para "nenhuma das
anteriores". Decidir também qual modelo do catálogo atual (`model_router.py`)
serve de candidato inicial para latência baixa (ex. Groq `gpt-oss-20b` ou
Gemini `flash-lite`, ambos já cadastrados). Rollback: nenhum, não há código.

**Etapa 1 — instrumentação antes de qualquer mudança de comportamento.**
Adicionar só um log (sem decisão nova) que registra toda frase que hoje cai em
`_looks_like_unhandled_local_action` (recusa) e toda frase que hoje escapa
para `orchestrator.process_message` mas contém sinal amplo de linguagem de
ação (heurística só para telemetria, não decide nada, não muda resposta).
Objetivo: ter uma lista real de frases do Alex que falham hoje, em vez de
desenhar o prompt do classificador contra casos hipotéticos.
Rollback: apagar a linha de log; zero risco funcional porque nada no
comportamento de resposta muda.

**Etapa 2 — construir o classificador isolado, sem plugar na cadeia.**
Escrever a função de classificação (ex. `classify_intent_with_llm(text,
allowed_actions) -> (action, param) | None`) como peça isolada e testável,
sem que `ipc_handlers.py` a chame ainda. Testar offline com os casos reais
coletados na Etapa 1, e medir a latência real da chamada (skill
`medir-latencia-da-zara`), não estimar.
Rollback: apagar a função nova; nenhum comportamento em produção muda porque
ninguém a invoca.

**Etapa 3 — plugar o fallback só no caminho de TEXTO, atrás de uma flag.**
No ponto exato onde `_looks_like_unhandled_local_action` hoje decide recusar,
inserir a chamada ao classificador da Etapa 2, atrás de uma variável de
configuração que pode ser desligada sem deploy. Testar as mesmas frases da
Etapa 1, por texto. Teste físico nível 1 (micro smoke): 1 a 3 frases
reformuladas que hoje falham, no candidato exato, com
`ALEX_OPEN_THIS_EXE:` nomeado.
Rollback: desligar a flag — a cadeia volta a ser 100% regex + guarda, sem
reverter nenhum arquivo.

**Etapa 4 — espelhar no caminho de VOZ só depois do texto estável.**
Mesma invariante que já vale para todo o resto do dispatcher: intent novo
entra nos dois lados juntos, nunca só num. Repetir a mesma etapa 3 no caminho
de voz, testando a MESMA frase por voz e por texto no mesmo build (regra de
`physical-validation.md`).
Rollback: mesma flag da Etapa 3, desliga nos dois caminhos ao mesmo tempo.

**Etapa 5 — ajuste fino, só depois de 3 e 4 estáveis por um tempo de uso real.**
Refinar prompt, exemplos e limiar de confiança com base em erro real
observado, não antes. Isso é ajuste de parâmetro sobre uma peça que já existe,
não redesenho — mas continua sendo uma frente por vez: um lote pequeno de
ajuste, retestar, só então o próximo lote.

**Nota de propriedade de arquivo (regra `time-zara.md`):** as Etapas 1 e 3
tocam `core/ipc_handlers.py` e `core/pc_voice_intent.py`, área do
ENGENHEIRO_EXECUCAO. Se a Etapa 2 optar por reusar `model_router.py` para
fazer a chamada de classificação (em vez de uma chamada direta isolada), esse
arquivo é área do ENGENHEIRO_LATENCIA — precisa de trava nomeada do CEO_MENTOR
para essa tarefa específica, não deve ser decidido sozinho por quem estiver
implementando.

---

## (e) Recomendação

Começar pela **Abordagem 3 (híbrida)**, e dentro dela pela **Etapa 0 e 1**
(contrato + instrumentação) antes de escrever qualquer chamada de modelo.

Razões:

- A Abordagem 1 entra em conflito direto com a prioridade #2 que o próprio
  Alex definiu no mesmo dia (latência mínima) e com a Lei Arquitetural do
  projeto (reflexo local não pode depender de rede/Supercérebro). Não deve
  nem ser tentada agora — faria o produto pior nas duas frentes que ele
  pediu simultaneamente.
- A Abordagem 2 sozinha não resolve o que foi relatado: o Alex não quer mais
  sinônimos, quer não precisar pensar em como falar.
- Hoje ninguém tem uma lista real de frases que falham — só a queixa geral
  ("não gosto de ter que falar sempre do mesmo jeito"). Desenhar o prompt do
  classificador contra casos inventados é decidir no escuro; a Etapa 1 é
  barata, não muda comportamento nenhum, e transforma a queixa em dado.
- O fallback da Abordagem 3, por desenho, só entra depois que toda a cadeia
  determinística atual (jarvis multi-action, lembrete, memória operacional,
  auto-conhecimento, arquivo, intent de PC composto, intent de PC simples, e
  o guarda honesto) já tentou e falhou — não compete com a ordem fixa de
  Fase 1 do projeto (voz Kore → latência → microfone → voz-ação), porque não
  toca nem em voz, nem em áudio, nem no caminho quente de latência. Pode ser
  investigado em paralelo, como leitura e prova de conceito, sem atrapalhar
  o que já está em andamento.

**O que esta proposta não decide:** qual modelo exato usar no fallback,
formato final do prompt, e se o classificador deve reusar `model_router.py`
ou ter um caminho próprio mais enxuto. Isso é trabalho da Etapa 0, com dado
real da Etapa 1 — não deveria ser fixado antes de existir o log de frases que
realmente falham hoje.
