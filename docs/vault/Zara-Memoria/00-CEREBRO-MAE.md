---
title: ZARA — Cérebro Mãe
category: system
zara_memory_role: canonical-guidance
---

# ZARA — Cérebro Mãe

Esta pasta é a memória compartilhada de orientação da ZARA e do ZARA Lab.

## Como usar

- **Fatos**: informações confirmadas sobre Alex, a ZARA e o projeto.
- **Decisões**: escolhas aprovadas pelo proprietário.
- **Missões**: objetivos, resultados e aprendizados do Lab.
- **Skills**: capacidades descobertas, testadas e versionadas.
- **Pesquisas**: fontes externas e evidências que ainda precisam de revisão.
- **Arquitetura**: como a ZARA funciona e quais são seus limites.

## Regra de verdade

Código atual e testes recentes têm prioridade sobre notas antigas. Uma nota é contexto e memória; não é prova de que uma capacidade está funcionando.

## Regra de segurança

Não guardar senhas, chaves, tokens, dados privados desnecessários ou raciocínio privado. Toda ação deve passar pelos controles do backend, permissões e verificações reais.

## Fluxo de aprendizado

```text
observação → registro → revisão → decisão → skill/código → teste → memória
```

## Fontes conectadas

A aplicação combina esta pasta com memória do usuário, memória do projeto e lições verificadas do Lab. O índice SQLite é apenas um cache de busca; as notas continuam sendo a fonte humana de orientação.

## Estado atual

A integração é best-effort: se o vault estiver indisponível, a ZARA continua funcionando com as outras memórias e informa estado degradado. A sincronização acontece sem exigir que o Obsidian esteja aberto.
