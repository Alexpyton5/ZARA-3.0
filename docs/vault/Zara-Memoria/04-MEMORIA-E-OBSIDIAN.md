---
title: ZARA — Memória e Obsidian
fonte: memory/project_memory.py e core/obsidian_bridge.py
---

# Memória e Obsidian

A memória de projeto da ZARA usa SQLite e Markdown em `%LOCALAPPDATA%\ZARA3\data\project-memory\`. Ela possui documentos de estado, arquitetura, decisões, roadmap e charter.

Quando o Obsidian está configurado, `ProjectMemory` detecta o vault pelo arquivo de configuração do Obsidian e espelha documentos na pasta `Zara-Memoria`. A ponte genérica `ObsidianBridge` também mantém um vault local compatível para o Galaxy.

A integração é uma **projeção/mirror**, não uma autorização para jogar todo o cofre em todos os prompts. A ZARA deve recuperar somente memória relevante, limitada e com proveniência.

Este diretório contém o pacote inicial de Markdown para sincronização:

- `00-INDICE.md`
- `01-ARQUITETURA.md`
- `02-ESTADO-ATUAL.md`
- `03-REGRAS-E-VALIDACAO.md`
- `04-MEMORIA-E-OBSIDIAN.md`

O caminho físico do vault real do usuário não foi confirmado nesta sessão porque o terminal Windows não respondeu. Portanto, estes arquivos são um pacote local pronto; não devem ser chamados de sincronizados no Obsidian físico até o caminho ser confirmado.
