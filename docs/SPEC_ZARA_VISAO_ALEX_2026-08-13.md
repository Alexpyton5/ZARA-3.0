# ESPECIFICAÇÃO — ZARA, a Jarvis da vida real

**Data:** 2026-08-13
**Origem:** entrevista `/grillme` com Alex, 17 rodadas, 2026-08-13
**Autoridade:** Alex. Este documento registra a visão dele, não a minha.
**Regra deste documento:** nenhuma linha de código. Só regras de negócio e decisões.

---

## 1. O ALVO

> "Sabe o filme, o Jarvis? Ela tem que chegar o mais perto possível daquilo.
> Não é um chatbot que responde rápido e abre YouTube não."

A ZARA não é uma assistente de comandos. É uma presença permanente que conhece o Alex,
lembra de tudo, tem opinião, personalidade e controla os aparelhos dele.

**Definição de perfeição, dada por Alex:**

1. Uma conversa longa e humanizada.
2. Controle de 100% do computador — qualquer coisa que ele disser, ela faz.

**Sonho declarado:** construir a melhor Jarvis do mundo e vendê-la.

---

## 2. A DOR QUE ORIGINOU TUDO

Registrado nas palavras dele, porque é o que este projeto tem que resolver antes de
qualquer feature:

- ela demora pra responder;
- ela não entende direito o que ele fala;
- ela começa a falar sozinha / se ouve;
- toda semana o ciclo se repete: **cria → codifica → funciona → quebra → perde função**;
- volta sempre pro nível básico de qualquer "Jarvis de YouTube": responder pergunta,
  abrir site, volume, brilho, calculadora;
- a pasta enche de lixo que ele não sabe pra que serve;
- ele não é programador, só tem a ideia de como quer.

> "Cansativo. Eu desisto dela quando vejo passar dias codificando e queimando tokens
> e ela parece não sair desse lugar."

**Consequência para o projeto:** *regressão é o inimigo número um*. Uma função nova que
quebra duas antigas é prejuízo, não progresso.

---

## 3. PERSONALIDADE E COMPORTAMENTO

### 3.1 Identidade

- Nome: **ZARA**. Palavra de ativação: "Zara".
- Voz: **feminina**. (Decisão de Alex, mantida mesmo com o Jarvis do filme sendo masculino.)
- Personalidade: **igual ao Jarvis** — irônica, formal, piada seca. **Pode zoar o Alex.**
- Idioma: **português do Brasil**. Inglês não é objetivo.

### 3.2 Iniciativa

Alex mudou de posição durante a entrevista, e a posição final é a que vale:

- **Posição inicial:** "sempre eu que começo a conversa", "obedecer e calar".
- **Posição final:** "deixe ela igual ao Jarvis", "pode ser igual à Jarvis em tudo".

**Regra final:** a ZARA é **proativa**. Ela pode puxar assunto, avisar de coisas, opinar
sem ser perguntada e discordar do Alex.

### 3.3 Interrupção

- Ela **espera o Alex terminar de falar**. Não corta a fala dele por qualquer coisa.
- **Exceção:** urgência real — algo quebrando, risco de perder trabalho. Aí ela pode cortar.
- *Decisão tomada pelo Mentor, não por Alex. Sujeita a revisão dele.*

### 3.4 Domínio da opinião

- Trabalho e computador: domínio dela. Pode opinar à vontade.
- Vida pessoal: **aconselha uma vez e para**. Exemplo aprovado por Alex:
  "Alex, você está dormindo pouco." Insistir e discutir, não.

> "Ela é aquela que deve cuidar do meu computador e do meu trabalho.
> Vida pessoal já é um pouco evasivo."

---

## 4. MEMÓRIA

> "Ela tem que lembrar pra sempre de tudo o que a gente conversou.
> A memória dela tem que ser melhor do que a de um humano, mas funcionar da mesma forma."

### Regras

- **Permanente.** Nada expira por tempo.
- **Funciona como memória humana:** o que importa vem à tona sozinho no momento certo;
  o resto fica guardado sem poluir a conversa. Não é um banco de dados que ela consulta
  quando mandam — é contexto que ela já tem.
- **Auditável.** A memória dela é gravada em arquivos de texto que o Alex consegue abrir e
  ler. Nada de caixa preta.
- **Integração com Obsidian:** nos **dois sentidos**.
  - ela **escreve** a memória dela como notas, que viram material do Alex;
  - ela **lê** o vault dele, pra saber dos projetos sem ele precisar contar.
  - *Decisão delegada ao Mentor por Alex ("faça o melhor para ela ser mais inteligente").*
- Exemplo concreto dado por ele do que ela precisa saber sem ser lembrada:
  **"estou trabalhando em um projeto ZOE".**

---

## 5. VOZ E ESCUTA

- **Microfone sempre ligado**, ouvindo em segundo plano.
- Ela só entra quando chamada por "Zara". Não responde a conversa aleatória.
- **Nunca pode entrar em loop com a própria voz.** Esse é um defeito atual reconhecido.
- Latência alvo: **menos de 1 segundo** entre o fim da fala dele e o começo da fala dela.
  - *Alex pediu "raciocínio igual ou melhor que um humano". Velocidade de resposta perto do
    humano é alcançável; raciocínio melhor que humano não é, e isso foi dito a ele.*

---

## 6. CICLO DE VIDA NO WINDOWS

- **Inicia junto com o Windows.**
- Fica rodando **em segundo plano**, invisível.
- Ao ser chamada, **abre a interface**.
- Depois de **10 minutos sem uso**, esconde a interface sozinha e volta ao segundo plano.

> "Outra coisa chata é ter que ficar abrindo a ZARA."

---

## 7. CONTROLE DO COMPUTADOR

### 7.1 Ela enxerga a tela

**Confirmado por Alex.** Ela não dispara comandos às cegas — ela lê o que está na tela:
títulos, miniaturas, botões, onde está o "pular anúncio".

### 7.2 Navegador

- Ela usa **o Chrome do Alex, com a conta dele logada**, na mesma janela que ele está olhando.
- Não é uma janela separada. Playlist baseada no gosto dele só existe com a conta dele.

### 7.3 Controle de site — o caso YouTube (exemplo canônico dado por ele)

- entrar no YouTube;
- ele fala um tópico, ela busca;
- ele escolhe um vídeo **que viu num card na tela**, ela abre;
- pular anúncio;
- pular música, play, pause;
- **resumir um vídeo pra ele**;
- conhecer as músicas que ele gosta e montar playlist com base no que ele ouve.

### 7.4 Arquivos e pastas

- abrir pastas, clicar, descer, organizar arquivos e pastas por voz;
- motivo declarado: *"ter que digitar isso é muito chato, ter que clicar"*.
- **Ela decide sozinha o critério de organização.** Não precisa mostrar plano antes.
- **Desfazer é obrigatório.** "Zara, desfaz isso" tem que voltar tudo como estava.
  > "É bom ter a opção de mandar ela desfazer, nunca se sabe né."

### 7.5 Câmera

Dois usos, ambos desejados:

1. **Gestos com a mão** para controlar o PC: rolar a tela, mover o mouse, dar zoom,
   fechar página. *"Seria incrível."*
2. **Mostrar algo na mão** pra ela: ela identifica o objeto ou pesquisa sobre ele.

---

## 8. LIMITES DE SEGURANÇA

### Nunca sem consultar o Alex

- **apagar qualquer coisa**;
- **comprar qualquer coisa**.

### Quando ela não entende

**Ela confirma antes de agir.** "Você quis dizer abrir o YouTube?" e espera o sim.
Escolhido por Alex sobre as alternativas de chutar ou só dizer "não entendi".

---

## 9. MULTI-DISPOSITIVO

> "Quero uma Jarvis da vida real que eu possa controlar todos os meus dispositivos:
> celular, tablet, computador. Tudo instalado, todos com as mesmas funções, e que se
> conectem. Para eu não precisar mais pegar no computador — só falar e mexer em tudo."

### Decisão arquitetural: um cérebro, vários corpos

A ZARA **existe uma vez só**. Ela mora no PC. Celular e tablet são **terminais** — ouvidos,
olhos e boca dela, não cópias dela.

**Por que assim:**
- memória única e idêntica em todo lugar, porque não existe sincronização — é a mesma ZARA;
- funções idênticas em todo aparelho, porque quem executa é sempre o mesmo cérebro;
- custo zero viável: um cérebro de graça, não três.

**Limitações honestas, registradas:**
- se o PC estiver desligado, os terminais ficam mudos;
- ações **dentro** do celular (abrir app do celular, ler notificação) exigem um agente no
  próprio aparelho — fase posterior, não faz parte do primeiro alvo;
- **iPhone e iPad não permitem** esse nível de controle. Android permite. Se os aparelhos do
  Alex forem Apple, essa parte da visão fica limitada por decisão da Apple, não por
  limitação do projeto. **Ponto em aberto: descobrir quais aparelhos ele tem.**

---

## 10. CUSTO — A RESTRIÇÃO MAIS DURA DO PROJETO

> "A conta é zero. É muito fácil fazer uma assistente virtual com API torrando dinheiro.
> O seu desafio é esse: fazer ela totalmente de graça, com tudo o que tiver de grátis."

### Regras

- **Custo mensal de operação para o Alex: R$ 0.** Não é meta, é requisito.
- Arquitetura escolhida por Alex: **misturada**.
  - **reflexo local** — volume, brilho, abrir pasta, abrir site: dentro do PC, instantâneo,
    sem internet, sem cota, **nunca depende de nuvem**;
  - **conversa e raciocínio** — camada gratuita de nuvem;
  - quando a cota acaba, ela **avisa e para** de conversar, mas **continua controlando o PC**.
- **Suporte a chave de qualquer modelo.** Quem quiser usar a própria API paga, usa.
  Alex não compra nenhuma.
- Alex não sabe mais o que está configurado hoje ("no meio da bagunça eu já nem sei").
  **Descobrir isso é tarefa do Mentor, não dele.**

### Colisão conhecida, registrada como problema em aberto

A voz **Kore** vem do Gemini Live, que tem cota. "Custo zero" e "Kore sempre" são
incompatíveis. Solução a definir: voz feminina gratuita e ilimitada para o dia a dia,
Kore quando a cota permitir. **Não resolvido neste documento.**

---

## 11. PRODUTO

- **Modelo:** assinatura mensal.
- **Mercado:** Brasil, em português.
- **Prazo:** nenhum. *"Fica pronta quando ficar boa."*
- **Custo por cliente para o Alex:** zero. Cada cliente usa chave gratuita própria ou o
  modo local. Assinatura sem custo recorrente por usuário.
- **A interface é o carro-chefe da venda.** A versão atual *"não está nem perto"* do que ele
  quer. **Mas é a última coisa a ser feita**, por decisão dele.

---

## 12. MÉTODO DE TRABALHO ACORDADO

- **Rede de proteção primeiro.** 2 a 3 dias construindo testes automáticos que travam
  regressão, antes de função nova. Escolhido por Alex sobre as alternativas.
  - Motivo: se algo quebrar volume, brilho ou YouTube, o teste acusa **antes** de chegar nele.
- **Alex testa quando der**, não na hora. Então o Mentor não pode ficar bloqueado esperando
  teste físico — precisa de cobertura automática e entregas em blocos.
- **Congelamento total foi recusado por Alex:** *"Nem pensar, já perdi tempo demais patinando."*
- **Limpeza de código morto/duplicado: autorizada, mas adiada.** Nada deve ser apagado agora.
  > "Não precisa apagar nada agora não. Mas deixa pra depois, eu gosto de organização na pasta."

---

## 13. IDEIAS DESCARTADAS E O MOTIVO

Registro obrigatório do que foi recusado durante a entrevista, para não voltar à mesa.

| Ideia | Quem descartou | Motivo |
|---|---|---|
| Congelar features por dias para estabilizar | Alex | "Já perdi tempo demais patinando" |
| Apagar código morto agora | Alex | Não é prioridade; fica para uma tarefa própria depois |
| ZARA puxar assunto sozinha (versão inicial) | Alex, depois **revertido** | Ele mudou para "igual ao Jarvis", que é proativo |
| ZARA obedecer e calar | Alex, depois **revertido** | Mesma reversão acima |
| ZARA insistir/discutir sobre vida pessoal dele | Alex | "Indagar eu acho um pouco demais" |
| ZARA cortar a fala do Alex livremente | Mentor | Ele disse "ela não pode me interromper"; mantido salvo urgência |
| Mostrar plano antes de organizar arquivos | Alex | "Ela decide sozinha" — mas com desfazer obrigatório |
| Janela separada do Chrome só pra ela | Alex | Playlist e histórico exigem a conta logada dele |
| Comprar qualquer API paga | Alex | Requisito de custo zero |
| Assinatura com custo recorrente por cliente | Mentor | Cada venda viraria prejuízo mensal |
| Inglês / mercado mundial agora | Alex | Foco em Brasil e português |
| Interface bonita agora | Alex | É o carro-chefe da venda, mas fica por último |
| "Raciocínio melhor que o humano" | Mentor | Não é alcançável hoje; foi dito a ele na entrevista |
| Nota 0–100 auto-atribuída como prova de que funciona | Mentor | É falso sucesso com número; só teste real prova |

---

## 14. O QUE AINDA NÃO SE SABE

Seção obrigatória. Nenhum plano deve tratar isto como resolvido.

- **Quais aparelhos o Alex tem** (Android ou Apple). Decide se a visão multi-dispositivo é
  viável ou capada.
- **Qual é o hardware do PC dele** (placa de vídeo, RAM). Decide o quanto de cérebro cabe
  rodar local. **O Mentor descobre, não pergunta.**
- **O que está configurado hoje** — quais APIs gratuitas, quais modelos locais.
  **O Mentor descobre, não pergunta.**
- **Como resolver a colisão Kore × custo zero.**
- **Se a cota gratuita de nuvem aguenta uso diário real** de conversa longa + visão de tela.
  Não medido. `NÃO PROVADO`.
- **Se ver a tela o tempo todo é viável de graça.** Visão custa caro em qualquer camada
  gratuita. Provavelmente exige leitura local da tela em vez de mandar imagem pra nuvem.
  Não medido. `NÃO PROVADO`.

---

## 15. CONDIÇÃO DE SUCESSO

Não é quantidade de função. É isto:

> Alex fala. A ZARA entende, lembra de quem ele é, executa de verdade no Windows,
> confere se deu certo, e **diz a verdade** sobre o que aconteceu.

E, acima de tudo:

> **Na semana seguinte, ela ainda faz tudo que fazia na semana anterior.**
