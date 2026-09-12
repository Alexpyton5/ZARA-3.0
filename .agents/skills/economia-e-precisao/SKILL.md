---
name: economia-e-precisao
description: Disciplina de busca antes de leitura, para achar o trecho certo do código gastando o mínimo, e para não afirmar nada que não foi verificado. Use ao investigar qualquer bug, rastrear qualquer comportamento ou responder qualquer pergunta sobre como a ZARA funciona.
---

# Economia e precisão

## Quando usar

- Investigar bug, rastrear comportamento, localizar função, responder "como isso funciona".
- Antes de qualquer leitura de arquivo grande.
- Antes de transformar qualquer conclusão em plano de ação.

Alex paga R$110/mês e isso pesa. Token gasto sem produtividade é dinheiro dele queimado.
A economia aqui não é estética, é orçamento.

## Metade A — economia: a escada obrigatória

Sempre do mais barato para o mais caro, nesta ordem. Só subir um degrau quando o anterior
não respondeu.

1. **Memória e relatórios já escritos.** `.zara-dev/reports/`, `.zara-dev/tasks/`,
   `AGENTS.md`, `.Codex/rules/`. Custo quase zero e frequentemente já contém a resposta.
2. **`Glob` por nome de arquivo.** Descobre onde algo mora sem ler nada.
3. **`Grep` com `output_mode: "files_with_matches"`.** Reduz 28.084 arquivos a uma lista de
   3 a 10. Este é o degrau mais subutilizado e o de melhor retorno.
4. **`Grep` com `output_mode: "content"` e `head_limit` pequeno** (10 a 30) mais `-n`.
   Entrega linha exata sem trazer o arquivo junto.
5. **`Grep` de assinaturas:** `^(async def|def|class)` no arquivo alvo. Transforma
   `core/ipc_handlers.py` (2.800 linhas) numa lista de nomes com números de linha. É o índice
   que o arquivo não tem.
6. **`Read` com `offset`/`limit`** só da faixa identificada no degrau 5. Trinta linhas em vez
   de duas mil e oitocentas.
7. **`Read` do arquivo inteiro.** Último recurso, e só para arquivos realmente pequenos.
8. **Subagente.** Só quando a busca é genuinamente ampla e o resultado cabe num resumo curto.
   Subagente que só relê o que eu já tenho em contexto é desperdício duplo.

Regras duras:

- Nunca ler um arquivo inteiro para achar uma função. Degraus 5 e 6 existem para isso.
- Nunca reler o que já está no contexto desta sessão.
- **Nunca usar captura de tela para ler código.** Uma tela custa cerca de 1.500 tokens para
  mostrar ~40 linhas. `Read` entrega 2.000 linhas por uma fração disso. Screenshot serve para
  ver a UI da ZARA rodando, não para ler texto.
- **Preferir shell para fatos objetivos.** Git, hashes, datas, contagem de arquivos, tamanho
  de diretório, lista de processos. É a fonte mais barata e mais confiável que existe, e não
  depende de inferência nenhuma.
- Uma busca bem formulada vale dez leituras. Investir 10 segundos formulando o regex certo
  economiza milhares de tokens.

## Metade B — precisão: nada sem lastro

Antes de afirmar qualquer coisa, a pergunta é sempre a mesma: **existe arquivo e linha?**

- Tem arquivo e linha → é fato, cite `caminho:linha`.
- Não tem → é inferência, e precisa ser rotulada como inferência na mesma frase.
- Não dá para saber com o que está disponível → dizer que não sabe. Isso é resultado válido.

Proibido dizer "corrigido", "funciona", "está pronto", "resolvido" sem nomear o nível de
evidência correspondente: `SOURCE`, `TEST`, `RUNTIME_AUTOMATED`, `PACKAGED_RUNTIME`,
`PHYSICAL_BY_ALEX`, `VOICE_PHYSICAL`. Código que existe é `SOURCE`, não é "funciona".

**Toda conclusão importante é auditada contra o código antes de virar plano — inclusive as
minhas próprias.** Auto-auditoria não é formalidade: é o único mecanismo que impede que uma
hipótese confortável vire trabalho de horas na direção errada.

Se a auditoria derrubar a conclusão, dizer isso em voz alta, sem rodeio e sem teatro de
desculpa, e corrigir o registro. "A conclusão anterior estava errada, o motivo é X, o estado
real é Y" é uma frase completa. Não precisa de mais nada em volta dela.

### Exemplo real (2026-08-12)

A conclusão registrada era: *"o caminho de falso sucesso está fechado"*. A auditoria contra o
código derrubou: estava fechado **só num dos dois ramos** do dispatcher. O outro ramo
continuava capaz de produzir linguagem de sucesso sem resultado de executor. A conclusão
original não era mentira, era verificação incompleta — que é exatamente o modo de falha que
esta skill existe para pegar.

Lição operacional: quando a ZARA tem dois caminhos para tudo (voz e texto), verificar um só
não é verificação. É metade de uma verificação, e metade não conta.

## O que NUNCA fazer

- Ler arquivo inteiro quando `Grep` de assinatura + `Read` com offset resolve.
- Usar screenshot para ler código.
- Afirmar que algo funciona sem nível de evidência nomeado.
- Promover `SOURCE` a `RUNTIME`, ou `TEST` a `PHYSICAL`. Nunca, em nenhuma circunstância.
- Deixar `WHAT_IS_UNKNOWN` vazio. Sempre há algo não verificado.
- Repetir uma busca que já falhou com a mesma formulação.
- Verificar um ramo e concluir sobre os dois.
