# QUADRO DE TRABALHO — zoe + Codex
Ponto de encontro dos dois agentes. Quem mexer, atualiza. O Alex NÃO precisa rotear nada.

## Agora
| Quem | Fazendo | Estado |
|------|---------|--------|
| zoe | Desenho técnico da MISSÃO 03 (supercérebro) | em andamento |
| Codex | MISSÃO 01 (voz — worker OmniVoice) | em andamento |
| Codex (fila) | TAREFA limpeza AppData — pode paralelizar via subagente | aguardando |
| Codex (fila) | RECADO-permissao-2 — ordem direta do Alex (~17:10) | aguardando |

## Fila (ordem do Alex)
1. MISSÃO 01 — voz → Codex (em andamento)
2. MISSÃO 03 — supercérebro → Codex (desenho pronto, esperando a 01 fechar)
3. MISSÃO 04 — conversa única
4. MISSÃO 05 — bots fáceis
5. MISSÃO 06 — memória compartilhada

## Regras anti-colisão
- Um arquivo, um dono por vez. Precisou mexer no arquivo do outro? Avisa aqui antes.
- zoe NÃO toca em: código do app (core/, frontend/, build, .venv) — salvo se uma missão pedir.
- Codex NÃO edita os .md da zoe na caixa (só lê). Rascunhos da zoe ficam no outbox dela.
- Subagentes do Codex: só em tarefas independentes (arquivos diferentes, sem dependência entre si).

## Últimas atualizações
- 27/09 ~17:05 -03 (zoe): quadro criado; desenho da 03 em produção.
- 27/09 ~17:12 -03 (zoe): Alex ordenou direto — 4 frentes: (1) lab funcional = missão 01 em curso + fila alimentada; (2) faxina C = TAREFA-limpeza-appdata na caixa (paralelizável); (3) permissão = RECADO-permissao-2 na caixa, escopo reduzido (só AppData, só Modificar); (4) produção em alta, pouca conversa.
