# Design da ZARA — decisões fechadas

Decidido com Alex em 2026-08-15, olhando telas reais e não descrição.
Nada aqui é palpite meu: cada item foi apontado por ele ou aprovado por ele.

## Por que existiu esta conversa

Ele: *"eu olho pra ZARA hoje e eu falo, não é isso que eu quero, é feio, é sem
graça, é ultrapassado... eu quero que você me dê algo que eu diga caralho que
interface foda. Que as pessoas vejam e digam eu preciso ter isso, eu preciso
comprar esse produto. Eu pago caro."*

E o combinado de método: *"eu não faço a mínima ideia sobre design... é só te
dizer o que eu quero, e aí você vai fazendo e eu vou dizendo, é isso, não é
isso, pode ser melhor."* Ele não estuda design. Eu mostro, ele aponta.

## A tese

**A interface mostra a prova.** A ZARA passou meses sendo construída para nunca
dizer que fez algo sem verificar. Nenhum concorrente mostra isso na tela. Então
o elemento mais forte do desenho é o carimbo de *verificado*, com o tempo que
levou — e a falha aparece com o mesmo destaque do acerto.

Isso não é enfeite: é a lei do projeto virando desenho, e é argumento de venda
enquanto a pessoa só olha.

## Paleta — fechada

Dois temas, o mesmo desenho. Segue o Windows: claro de dia, escuro de noite.

| tema | fundo | destaque |
|---|---|---|
| **Militar escuro** (noturno) | `#0B0F0B` | `#8FC17F` |
| **Papel** (claro) | `#FAFAF6` | `#1B4D3E` |

O verde é escolha pessoal dele — *"eu escolhi verde pq me identifico muito com o
verde, porem o verde tem que ser oliva ou militar"*.

Todo o resto da tela (painel, borda, texto, texto fraco) é **derivado** dessas
duas cores por mistura. Consequência prática, e ela é dele: o produto pode sair
com vários temas e cada pessoa escolher o seu, sem o desenho quebrar.

## Regras duras

1. **Uma cor de destaque só.** Nada mais brilha na tela. Se algo chama atenção,
   é porque aconteceu de verdade.
2. **A esfera continua, pequena, ao lado do nome.** Ela é criação do Alex e fica.
   Mas saiu do centro: bola grande e brilhante no meio é o clichê nº 1 de app de
   IA em 2026, e era o que fazia a ZARA parecer todas as outras.
3. **Duas famílias de letra, e elas significam coisas diferentes.** O que foi
   FALADO (por ele ou por ela) usa serifada, porque é linguagem. O que a máquina
   FEZ usa monoespaçada, porque é dado. A tipografia carrega a divisão central do
   produto.
4. **Erro tem o mesmo peso visual do acerto.** Esconder falha é o defeito que
   este projeto mais combate.

## A referência Apple — pesquisada pelo Codex em 15/08

Alex: *"eu sou muito fã do design de apps da Apple... traga pro nosso projeto
algo nunca visto mas que tenha referência forte dos designers da Apple"*.

### O achado que muda tudo

As diretrizes oficiais da Apple para assistentes dizem que, quando a pessoa não
está olhando, o **diálogo falado** carrega o resultado real, e a tela **não deve
repetir a fala** — ela guarda a evidência complementar: ação interpretada, alvo,
horário, pós-condição observada, detalhe expansível.

É a tese desta interface, escrita por eles. Não foi inspiração: foi convergência.
Fonte: HIG — Snippets, HIG — Siri.

### Copiar o visual seria copiar o que eles estão consertando

O efeito de vidro (Liquid Glass, 2025) está sendo **corrigido** em 2026 — mais
difusão, borda escurecida, controle de opacidade — porque prejudicava leitura.
Quem adotar agora chega atrasado num problema conhecido.
Fonte: WWDC26 Platforms State of the Union.

### O que se leva: o raciocínio

- *"Encanto não é confete jogado depois — é resultado de propósito, controle,
  segurança e execução correta."* (WWDC26, Principles of Great Design)
- *"Novo que pareça familiar no primeiro olhar; a surpresa só se revela no uso."*
  (Alan Dye, ex-Apple)
- Movimento é semântico, não recompensa. Sem dedo na tela, elasticidade perde
  sentido: o movimento da ZARA deve narrar `ouviu → executa → verificou/falhou`
  e **parar** quando o estado se resolve.
- Profundidade indica origem e elevação — um menu deve parecer nascer do controle
  que o abriu — não é enfeite.

### Regra nova, adotada daqui em diante

**Ação executada mas não verificada aparece como "não verificado" — nunca verde.**
Verde é exclusivo de prova real. É a lei do projeto virando cor.

### O que NÃO importar da Apple

- Geometria de dedo e cantos de aparelho. Cápsulas grandes só para estados
  decisivos (executando, confirmado, falhou); histórico e evidência pedem a
  densidade retangular do desktop.
- Transparência como protagonista. No Windows, Acrylic serve a superfícies
  transitórias e Mica/sólido às duradouras. O protagonista aqui é a prova.
- Proporções de iPhone numa janela grande de Windows — contraria o próprio
  princípio Apple de respeitar o contexto.
- `#8FC17F` sobre vidro: perde contraste. Ele é cor de **estado confirmado**,
  não cor de texto.

### As três referências que usam Apple sem parecer Apple

| referência | o que se leva |
|---|---|
| **Linear** (refresh 2026) | densidade alta com navegação recuada; só o trabalho central disputa atenção |
| **GitHub Actions** | estado inequívoco primeiro (rodando / passou / falhou), detalhe e log sob expansão |
| **Teenage Engineering OP-1** | cor como código operacional próprio, não tint decorativo — vale para o verde militar |

**Síntese:** Apple na disciplina · Linear na densidade · GitHub na prova ·
Teenage Engineering na personalidade.

## O que foi descartado, e por quê

- **Fluent 2 (recomendação do Codex).** Faz a ZARA parecer configuração do
  Windows. Ele quer parecer produto caro, não utilitário do sistema. Aproveitar
  só os materiais de fundo (Mica, Acrylic), que são nativos e dão profundidade.
- **Direção "Vitrine"** (tipografia enorme, fita de voz, alto contraste). Chama
  atenção e cansa rápido em uso diário.
- **Sálvia.** Boa, mas sem função depois que militar e papel ficaram sendo o par
  escuro/claro.
- **Tudo que o Codex listou como clichê de 2026** e que a ZARA tinha: esfera
  luminosa como identidade inteira, roxo-ciano, glassmorphism, sopa de cards
  arredondados, sidebar genérica de chat.

## Quando isto entra

Depois da latência. Interface bonita numa ZARA lenta não vende, e mexer nas duas
ao mesmo tempo quebra a regra de um delta causal por vez.

Referência viva das telas: artefato "Três ZARAs" (clica e personaliza).
