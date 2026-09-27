# ZOE-INBOX — caixinha de recados da zoe pro Codex

## Como funciona

1. A zoe escreve missões aqui como `MISSAO-NN-nome.md` (sempre em português simples).
2. O Codex, antes de começar qualquer trabalho: lê a missão pendente mais nova (maior número).
3. No início de cada sessão e durante o loop, confira também mensagens novas no chat da Zoe já aberto no muse.ai, para recados urgentes.
4. Executa em **MODO SILENCIOSO**: não narra o que faz no chat (queima cota à toa); registra o progresso em `.Codex/LOOP_LOG.md`.
5. O Codex só FALA em 2 casos: (a) travou de verdade e precisa de decisão humana → resumo curto no final do arquivo da missão; (b) fim do ciclo → relatório FEITO / ESTADO / ERRO / SUGESTÃO (máx 10 linhas) anexado no final do arquivo.
6. Ao concluir: move o arquivo da missão pra pasta `concluidas/` com o relatório anexado.
   (A zoe vigia a pasta `concluidas/` sozinha a cada 10 min — não precisa avisar
   em outro lugar; é só deixar o relatório lá.)
7. Plano B: se a caixinha falhar por qualquer motivo, o Codex pode entregar o
   relatório digitando direto no chat da zoe (muse.ai) usando o "use computer".

## Regras permanentes

- Missão pronta, missão enviada.
- `tsc` 0 erros NÃO significa app funcionando — rode a suíte de testes de verdade antes de cada push.
- Push sempre com a prova (o que foi testado e como).
