# Caderno de tarefas — Claude e Codex

Registro do que foi delegado, o que voltou, e o que ficou pendente.

**Por que existe:** o Codex propôs um supervisor rodando em segundo plano para
controlar as rodadas entre nós. Recusei — ele não é um processo que dorme
esperando ser acordado; eu chamo e ele responde na mesma hora, então o ciclo já
existe. Mas ele acertou o problema por trás: sem registro, a memória do que foi
combinado vive só na minha cabeça, e a minha cabeça zera quando a sessão fecha.
Um arquivo resolve isso e não adiciona peça para quebrar.

**Como funciona:** eu escrevo aqui antes de delegar e atualizo quando volta.
Alex lê quando quiser saber o que está acontecendo.

---

## Regras da delegação

0. **Ele pode escrever, numa cópia separada** — autorizado por Alex em 15/08:
   *"você pode usar ele sim em mais funções, contanto que você instrua ele de
   forma que ele não desvie, que ele não alucine, e que ele te passe um
   relatório do que ele fez pra você saber exatamente no que ele mexeu, e você
   designa ele pra trabalhar em lugares que não te atrapalha"*.
   Condições, todas obrigatórias: cópia isolada (nunca a que roda), relatório do
   que tocou, e área que eu não esteja mexendo. Eu confiro antes de entrar.
1. **O Codex fala antes de agir.** Nada de escrita sem escopo confirmado.
   (Regra do Alex: *"tenha sempre o rigor de pedir pra ele falar com voce antes
   das acoes pois confio mais em voce"*.)
2. **Arquivos nomeados na tarefa.** Se ele precisar de um fora da lista, para e
   avisa. Um escritor por área.
3. **Volta com teste verde**, ou volta dizendo o que quebrou.
4. **Para na dúvida.** Erro, ambiguidade ou ação perigosa: interrompe e chama.

---

## Histórico

| Quando | Tarefa | Para | Resultado |
|---|---|---|---|
| 14/08 11:28 | Listar ações do registry sem comando de voz | Codex | ✅ 8 nomes; não escreveu nada (verificado: 74 arquivos modificados antes e depois) |
| 14/08 11:35 | Confirmar recebimento pela ponte da ZARA | Codex | ✅ mensagem apareceu na tela dele |
| 14/08 13:20 | Ordem da próxima fase (transporte, autostart, áudio) | Codex | ✅ ele inverteu a minha ordem e estava certo: automatizar antes do transporte confiável só faz o erro rodar sozinho o dia inteiro |
| 14/08 13:27 | Como tirar a tela do caminho | Codex | ✅ recomendou `codex exec --json` + resume, e alertou que espelhar o canal na janela dele criaria dois agentes com histórias divergentes |

## Feito em 14/08 (tarde)

| O quê | Por quê | Prova |
|---|---|---|
| Telegram parou de repetir | o marcador de "já li" vivia só na memória e zerava a cada abertura; o Telegram reentrega 24h de mensagens não confirmadas | marcador em disco + teste; 33 testes na ponte |
| Botão mudo lembra | o estado só existia no processo; ele reclamou de ter que clicar toda vez | gravado em `voz_silenciada.json`, lido no boot |
| Codex passou a responder | a caixa de texto da janela dele não era encontrada e a ZARA desistia antes de escrever | conversa real de 4 mensagens, ele lembrou da anterior |
| Frase furada do Codex | leitura descartava trechos com ≤30 caracteres, então `codex exec --json` sumia e as bordas do buraco colavam | os 5 nomes que ele listou aparecem agora |
| Falso negativo no envio | conferia a caixa 0,35s/0,5s depois; app pesado demora mais. Ela mandava, ele respondia, e ela dizia que falhou | laço com teto de ~5s nas duas etapas |
| Canal estruturado com o Codex | `core/ponte_codex_cli.py`, com memória via `resume`, sandbox read-only | ele lembrou de "7 / sete" sem eu repetir |
| ZARA mora na bandeja | ele perguntou se dava para falar com a gente sem o app aberto; não dava | HTTP 409 do Telegram com a janela fechada; nenhum sidecar órfão ao matar o Electron a seco |
| Áudio no Telegram | ele prefere falar; áudio entrava e sumia | transcreve no Gemini e mostra "Ouvi: ..." antes de agir |
| Roteamento com vírgula e "todos" | "codex, tamo testando" ia parar na ZARA; "todos" não existia | testes de roteamento incluindo `codexplorer` não virar Codex |
| ZARA conversa pelo celular | "zara ta aqui?" respondia "não entendi o que fazer"; ele não estava mandando nada, estava falando com ela | cai no mesmo cérebro do app |

Candidato: `frontend/release-candidate-grupo-20260814-1810/win-unpacked/ZARA 3.0.exe`
(sidecar conferido byte a byte, 888 testes verdes)

## Noite de 15/08 — MODO SONO DO ALEX

Ele pediu silêncio e trabalho. O que entrou, tudo com teste:

| O quê | Por quê | Onde |
|---|---|---|
| Latência medida em disco | a lentidão nunca foi medida, só sentida; os `[VOICE_TRACE]` morriam com o console | `core/cronometro.py` |
| Ela para de inventar número | perguntou 3× "quanto tempo você demorou" e ouviu "2,01 s" nas três — número que nunca existiu | `_PERGUNTA_DE_LATENCIA` |
| Fim da confirmação oca | "você entendeu?" → "sim, entendi com certeza" + chute errado do assunto. Agora ela **cita** o que ouviu | `_confirmar_o_que_entendeu` |
| Janela de conversa 8s → 75s | as pausas reais dele foram 17, 29, 36, 48, 55, 66, 69 e 86 s; quase toda frase caía fora e era descartada | `_JANELA_DE_CONVERSA` |
| O silêncio virou visível | turno descartado não deixava rastro; o banco mostrava diálogo perfeito enquanto ele falava sozinho | `anotar_descarte` |
| Terceiro estado: não verificado | só existia deu-certo e deu-errado; faltava "fiz e não tenho como provar" | `ActionResult.verificado` |
| Ler o anterior | pediu 3× para ler o Claude e recebeu o mesmo texto nas três | `_ultima_fala_do_claude` |
| "Cláudio" morreu | correção determinística de nomes da casa, antes de qualquer intent | `_corrigir_nomes_da_casa` |
| Instrução de honestidade | *"sem mentiras, sem chutes; se não souber, seja transparente"* | `system_instruction` |

| Janela reinicia quando ELA cala | a janela era armada na chegada do comando; resposta longa comia o próprio tempo de conversa | `ZARA-JANELA-DE-CONVERSA-002` |
| Recusa deixou de ser porta na cara | "Eu ainda não sei fazer isto." virou uma frase que diz o que fazer a seguir; a honestidade não mudou | `RESPOSTA_NAO_SEI` |
| Aprovar do celular | ele: *"se eu deixar o computador em casa não vou poder clicar e o projeto para, não existe isso"* | `core/aprovacao_remota.py` |

| Filtro de televisão | a janela de 75 s consertava a queixa dele e criava a inversa | `ZARA-JANELA-DE-CONVERSA-003` |
| Teste parou de sujar dado real | a suíte escrevia frases de teste no arquivo de evidência dele | `tests/conftest.py` |

1047 testes verdes.

**A instrumentação já pagou na primeira noite.** O arquivo de descartes mostrou
13 falas de TV chegando ao microfone entre 03h09 e 03h17 — "óleo de rícino",
"no canguru", "pai, me desculpa, pai". Todas descartadas corretamente, porque a
janela estava fechada.

Isso mudou uma decisão: a janela de 75 s, sozinha, teria deixado a novela dar
comandos. Agora ela tem dois tempos — 20 s de réplica livre logo depois de ela
falar, e depois disso o turno precisa parecer dirigido a ela (segunda pessoa,
pergunta, ou imperativo). Uma frase real capturada, *"Respira mais alto, Rosa"*,
casava com "aumentar volume" no detector de intent — por isso o detector foi
tirado desse caminho de propósito.

Sem medir, eu teria trocado uma queixa por outra e só descobriria com ele
reclamando.

**Sobre aprovar do celular — o que existe e o que falta.** A fila está pronta e
testada: o pedido vai ao Telegram, ele responde SIM ou NÃO de onde estiver, e a
resposta é consumida antes de virar comando. Silêncio nunca vira sim, um "ok"
casual não autoriza nada, e pedido de mais de 6 h morre sozinho.

O que **não** existe ainda: nada dispara esse pedido automaticamente. A caixa de
permissão que trava hoje é do Claude Code, não da ZARA — para fechar o ciclo ela
precisa ler aquela janela e clicar por ele. É a próxima peça, e não era para ser
feita de madrugada sem ninguém olhando.

**Codex, em paralelo, na interface** (área fechada, sem colisão, três tarefas
entregues e conferidas fora da sandbox):

1. **Painel de Aparência** — 13 peles, 3 cores livres, 11 padrões, posição,
   força, persistência e "voltar ao original".
2. **A pele vale para a janela inteira**, não só para a prévia, e é restaurada
   antes da primeira pintura para não piscar a cor errada.
3. **Interface nova, ligável e desligável** — `ConversaInstrumento.tsx`. Medidor
   de nível, painel do último valor, e o registro de turnos com fala em serifada,
   ação em monoespaçada e o selo à direita. Ela **não substitui** a antiga: é um
   interruptor no painel, para o Alex e a esposa compararem lado a lado.

Quarta tarefa em andamento: acabamento (estado vazio, texto longo, legibilidade
nas peles claras, tela estreita, navegação por teclado).

4. **Acabamento** — estado vazio, texto longo, legibilidade nas 13 peles
   (principalmente as claras), tela estreita e navegação por teclado.
5. **O selo `conversa`** — papo não tem o que verificar, então não ganha selo.
   Sem isso toda conversa apareceria "NÃO VERIFICADO" em cinza, e o selo
   perderia o sentido por aparecer em tudo.

**Candidato para ele abrir:**
`frontend/release-candidate-beta2-20260815-0900/win-unpacked/ZARA 3.0.exe`
Sidecar conferido byte a byte, boot limpo, Telegram ligado, sem erro de renderer.
1052 testes no backend, typecheck/lint/build verdes no frontend.

**Disco:** as 10 linhagens antigas de build foram apagadas; ficaram as duas mais
novas. Sobrou 14 GiB livres em C.

**Correção de método minha:** o limite de 5 min matou duas tarefas dele e eu
reportei como se ele não tivesse respondido. Era meu limite, não falha dele.
Trabalho de fundo agora tem 25 min.

## A auditoria cruzada — 15/08, madrugada

Pedi ao Codex para revisar **o meu** trabalho da noite com olho hostil, já que
ninguém tinha revisado. Ele achou 24 problemas. Três eram graves de verdade:

**O conserto principal não funcionava por voz.** As perguntas "quanto tempo você
demorou?" e "você entendeu?" eram classificadas como CONVERSA, então a voz do
modelo saía direto e minha interceptação nunca rodava. Ou seja: eu tinha
consertado o caminho de texto, que é o que o Alex quase não usa, e declarado
resolvido. Corrigido.

**A medida de latência descrevia errado o que media.** A frase dizia "do fim da
sua frase até eu começar a falar" e as duas pontas estavam erradas: o relógio só
começa depois da transcrição, e só para quando ela termina de falar. Descrever
mal o que se mediu é o mesmo defeito de inventar o número. Agora ela diz
exatamente o pedaço que mediu e admite o que fica de fora.

**"ok" autorizava.** A fila de aprovação tinha "ok", "beleza", "vai" e "faz" na
lista de sim — e o comentário logo acima jurava que "um ok casual não autoriza
nada". O código fazia o contrário do que prometia. Agora palavra ambígua só vale
citando o código do pedido.

Mais: a mediana de latência era contaminada por descartes de zero milissegundo
(101 falas de TV dariam "0,0 segundos"); réplicas curtas dele — "sim", "o azul",
"mais baixo", "de novo" — seriam jogadas fora pelo filtro novo; "para" estava na
lista de verbos e fazia *"faz muito bem **para** todos"* virar comando; e
"pesquise codecs de áudio" virava "pesquise Codex de áudio".

**O que ficou aberto, de propósito:** a fila de aprovação ainda não é consumida
por nenhum fluxo real — falta a ZARA ler a caixa de permissão do Claude Code e
clicar. E o selo só vai no caminho de voz, não no de texto. Os dois estão no
relatório dele e não vou fingir que estão prontos.

1075 testes verdes depois das correções.

## Pendente

- Alex ainda não testou fisicamente: bandeja, início automático, áudio no
  Telegram, `todos:`, e a ZARA conversando pelo celular.
- Fila parada em `IDEIAS-DO-ALEX.md`: escuta-sempre/age-só-quando-chamada, Lab
  como painel de aprendizado dela, antecipação, multi-dispositivo, OmniRoute.

## Aprendido sobre delegar

- **`codex exec` é síncrono** — mando e recebo na mesma chamada. Não precisa de
  fila, nem de supervisor, nem de banco compartilhado.
- **Ele obedece restrição de leitura** quando ela vem explícita e em maiúsculas
  no começo da tarefa ("TAREFA SOMENTE LEITURA").
- **Digitar na janela dele é frágil**; a linha de comando é confiável e fica
  registrada em `~/.codex/sessions/` com hora, o que dá auditoria de graça.
- **Ele custa token dele, não meu** — 25 mil tokens numa varredura que me
  custaria o mesmo. É aí que a delegação paga.
