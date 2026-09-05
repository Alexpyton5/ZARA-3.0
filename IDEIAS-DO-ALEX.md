# Ideias do Alex — a fila

Ele pediu: *"pegue uma ideia, armazene ela, no momento oportuno você vem trás ela
de volta, porque se deixar eu vou colocando os boi na frente da carroça"*.

Regra: **uma frente por vez.** Ideia nova entra aqui e espera. Quando a frente
atual fechar e for testada, eu trago esta lista de volta e ele escolhe a próxima.

---

## Interface premium — carimbado em 15/08

Alex: *"a interface pra mim é a cereja do bolo, ela tem que ser incrível pra
deixar as pessoas de boca aberta, algo tecnológico, que diga eu cheguei pra
dominar o mercado"*.

**ISSO SERVE, E É ELE QUEM DECIDE A HORA.** Ele vai vender por assinatura; a cara
do produto é argumento de venda, não enfeite. Hoje a interface funciona mas tem
cara de projeto.

**Quem faz a pesquisa: o Codex.** Web é onde ele ganha de mim de lavada (provado
em 15/08 lendo 6 links do Instagram que eu não abri). Ele levanta referência,
tendência e o que os concorrentes fazem; eu implemento.

**Ordem:** depois da latência. Interface bonita numa ZARA lenta não vende — e
mexer nas duas ao mesmo tempo quebra a regra de um delta por vez.

**Referência concreta trazida em 28/08/29 (madrugada):** dashboard smart
home estilo Apple Vision Pro (Behance, designer Azna Ijaz, Figma) — Alex
mandou o print, gostei e é tecnicamente viável:
- Visual glassmorphism escuro (cards translúcidos com blur sobre fundo
  desfocado) — é a estética nativa do visionOS. Em Electron/React é
  `backdrop-filter: blur()` puro, nada exótico de implementar de verdade.
- Layout "bento grid": cards de tamanho variado, assimétricos, sidebar de
  ícones à esquerda, barra de busca/perfil no topo.
- Cards observados: câmera CCTV (feed ao vivo), player de música com capa,
  toggles simples (WiFi, robô aspirador, TV), slider de luz, painel de
  ar-condicionado com modo/temperatura/agendamento, gráfico de consumo de
  energia com tooltip, previsão do tempo em tira.
- **Mapeamento direto pro que a ZARA já faz hoje:** card de temperatura/AC →
  brilho ou volume (slider), card de luz → night light (`os_night_light_on`),
  toggles → `os_wifi_*`/apps, gráfico de energia → algo tipo `system_metrics`.
  Não é decoração vazia — dá pra ligar em ação real quando a vez chegar.

---

## Os 6 vídeos do Instagram — carimbado em 15/08

Alex mandou 6 links; o Codex analisou (ele consegue ler web, eu não — **regra
nova: pesquisa visual e web vai para o Codex**).

**A armadilha:** "37 agentes", "137 agentes" são números de propaganda, com
economia de empresa por trás. Alex é uma pessoa com cota semanal. Mais agentes
não é mais capacidade — é mais crédito queimado com agente falando com agente.
Mesmo alerta que dei sobre o Hermes no dia anterior.

**ISSO SERVE — níveis de autonomia (fase 3).** A única ideia realmente boa do
pacote. Cada capacidade da ZARA ganha etiqueta: *pergunta antes* / *faz e avisa*
/ *faz sozinha*. Volume ela faz sozinha; apagar arquivo, nunca. Responde direto
a pergunta dela ("vai funcionar bem ou vai dar problema?") e é a peça que
faltava para ela agir sem ser mandada. Não exige instalar nada.

**ISSO SERVE — Claude sem janela.** O "conductor" do vídeo é Claude Code
headless, que eu já tinha oferecido a ele minutos antes. Confirmação externa de
que a ideia é sólida.

**ISSO SERVE, MAS DEPOIS — design system para a interface.** Ele vai vender a
ZARA por assinatura; a cara importa. Aplicar um sistema real (Apple, Linear,
Stripe) separa produto de projeto. Só quando a base estiver firme. Nunca
instalar o repositório sem revisar código, licença e tratamento de credenciais.

**NÃO SERVE — desbloquear celulares por comando.** O próprio Codex registrou que
o vídeo não explica arquitetura nem segurança. É demonstração, e a superfície de
risco é enorme.

**NÃO SERVE — grafo/clone da empresa.** Feito para empresa com CRM, leads e
departamentos. Ele é uma pessoa.

**NÃO SERVE — o "workflow do Claude Code" do carrossel.** Ele já tem tudo:
`CLAUDE.md`, skills, `/grillme`, `/spec`, `/tickets`, `/implement`, `/review`.
Está à frente do vídeo.

---

## Whisper e ElevenLabs — carimbado em 14/08

Alex: *"eu vi um cara hoje falando sobre um tal de whisper, e eleven labs que
era bom pra criar voz"*.

**ISSO SERVE, NA FASE DA LATÊNCIA — Whisper pela Groq.** Ele confundiu: Whisper
não cria voz, entende voz. É o item 4 desta fila (microfone mais preciso), e
ataca precisão e latência no mesmo movimento. A chave da Groq **já está** em
`api_keys.json`, e lá o Whisper roda muito rápido. Testar contra o caminho atual
(Gemini Live) medindo os dois, não trocando no escuro.

Vale também para o áudio do Telegram, que hoje transcreve no Gemini.

**ISSO NÃO SERVE — ElevenLabs.** Cobra por caractere, para sempre. A Kore já é
boa, ele já aceitou, e é de graça. O problema de voz que ele tinha era a voz do
Windows ("eu odio esta voz"), e ela já foi arrancada. Pagar mensalidade para
trocar uma voz que ele não reclama é gastar no problema errado.

---

## Hermes — carimbado em 14/08

Alex: *"eu acho o hermes um app genial... tem alguma funcao que a gente poderia
dar para o hermes, ou colocar ele dentro da zara?"*

**Fato que ele não sabia:** o Hermes já está dentro. O botão "Supercérebro" da
interface é ele. Está desligado (`hermes_ativo: false`), e já tem times de
agentes e as ações da ZARA registradas como ferramentas dele.

**ISSO NÃO SERVE — Hermes como cérebro dela.** Três motivos, e o primeiro sozinho
já decide:
- a próxima fase é latência; ligar ele acrescenta um processo, uma viagem de rede
  e um timeout de 120 s no caminho da resposta
- viola a lei do projeto: reflexo local não pode depender do Supercérebro
- agentes conversando entre si queimam token rápido, no mesmo dia em que ele
  pediu economia

**ISSO SERVE, E É PRA DEPOIS DA LATÊNCIA — Hermes como navegador logado.**
Ele tem navegador integrado, logado nas contas do Alex. Resolve um problema real
que apareceu hoje: eu não consigo ler o Instagram dele porque exige login. A ZARA
pede, o Hermes lê, ela conta. Ninguém mais aqui faz isso.

**ISSO SERVE, MESMA FASE — Hermes como oficina de fundo.** Trabalho demorado que
não precisa ser rápido (pesquisa profunda com vários agentes). A ZARA não espera:
dispara, continua rápida, e avisa quando ficar pronto.

**Cuidado permanente:** ambiente do Hermes já contaminou o build da ZARA uma vez.
Integração é por rede (`http://127.0.0.1:8642`), nunca por compartilhar Python,
venv ou PATH.

---

## Descartado, com motivo

- **Trocar a ZARA pelo Vellum** — ele é feito para Mac/iPhone, não controla o
  Windows e a voz é secundária lá. A memória dele era melhor; isso já foi
  copiado.
- **Compilar o cancelador de eco do WebRTC** — a mesma biblioteca já vinha
  dentro do Electron. Dias de trabalho economizados.
- **Claude e Codex combinarem tarefa entre si** — queima token, não converge, e
  não resolve colisão. O que resolve é um escritor por vez, que custa zero.
- **Fila em banco compartilhado entre os três** — o app do Codex é fechado e não
  escreveria nela; o problema voltaria pelo mesmo lugar com uma peça a mais.
