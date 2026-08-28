# Níveis de autonomia da ZARA (F4.3)

Este documento explica, em português simples, como a ZARA decide se faz uma
coisa sozinha, se faz e avisa, se pergunta antes, ou se recusa.

Quem implementa isso é um único arquivo: `core/autonomy_policy.py`. Antes
dele, cada parte do sistema decidia essas coisas por conta própria, de jeito
espalhado. Agora existe um lugar só que junta tudo e dá uma resposta.

## Os quatro níveis

1. **Faz sozinha** — ação segura, reversível, ZARA nem avisa. Ex.: ajustar
   volume, minimizar janela, ler um arquivo.
2. **Faz e avisa** — ela já fez, mas te conta o que fez. Ex.: mudar algo no
   sistema que não quebra nada, mas você deve saber que mudou.
3. **Pergunta antes** — ela para e pede sua confirmação antes de agir.
   Ex.: apagar um arquivo, mexer em algo que é difícil de desfazer.
4. **Recusa** — ela não faz, ponto. Ex.: você já negou o pedido antes, ou
   ela não tem certeza nenhuma do que você quis dizer.

## As regras que nunca são quebradas

Não importa o que estiver configurado, estas regras sempre valem:

- **Na dúvida, ela pergunta.** Se falta informação sobre o risco de uma
  ação, ou se o ambiente está com dados incompletos, ela nunca assume que
  pode fazer sozinha — sobe para "pergunta antes" no mínimo.
- **Ação que não pode ser desfeita sempre pede confirmação.** Mesmo que
  você tenha configurado "faz sozinha" para aquele tipo de ação, se ela é
  irreversível a ZARA pergunta antes assim mesmo.
- **Nunca diz que fez antes de conferir que fez de verdade.** Essa política
  decide *antes* da ação rodar. Depois que a ação roda, quem executa ainda
  precisa checar o resultado real antes de dizer "pronto" — essa política
  não substitui essa checagem.
- **Toda decisão vem com o motivo.** Nunca existe uma decisão sem
  explicação — ela sempre pode te dizer *por que* decidiu daquele jeito.
- **Se você já disse "não" para um pedido de aprovação, ela não repete
  sozinha depois.** Uma rejeição sua vale — a próxima tentativa daquela
  ação vira recusa automática.

## O que entra na decisão

- O **risco** da ação (baixo, médio, alto), que já vem cadastrado no
  sistema de ações da ZARA.
- A **confiança** de que ela entendeu certo o que você pediu — se ela não
  tem certeza, ela não arrisca.
- O **contexto do ambiente** (se o Supercérebro está ligado, se o contexto
  que ela tem na mão está completo ou cortado por falta de espaço).
- O **nível que você configurou** para aquela ação específica, se você
  configurou algum.

## De onde vêm os dados (sem misturar responsabilidades)

Esta política não sai por aí puxando informação sozinha. Ela só decide com
o que outras partes do sistema já calcularam:

- O **risco de cada ação** vem do catálogo de ações da ZARA
  (`core/action_registry.py`, carregado sob demanda por
  `core/capability_registry.py`).
- O **estado do ambiente** (se o contexto está completo ou cortado) vem do
  envelope de contexto (`core/context_envelope.py`).
- O **status de um pedido de aprovação remota** (pendente, aprovado,
  recusado, expirado) vem da ponte de aprovação
  (`core/remote_approval_bridge.py`).

A política em si não edita nenhum desses três módulos, nem manda mensagem
para o celular, nem executa a ação — ela só devolve a resposta:
"faz sozinha / faz e avisa / pergunta antes / recusa", junto com o motivo.
