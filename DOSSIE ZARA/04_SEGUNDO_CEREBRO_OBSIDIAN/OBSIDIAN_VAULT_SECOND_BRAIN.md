# Segundo Cérebro da ZARA — Obsidian Vault

## Objetivo

A ZARA precisa possuir uma memória que cresce com o uso.

Tudo o que ela aprende, lê, ouve, observa, produz, resume ou descobre pode, quando permitido, ser transformado em conhecimento persistente no Vault.

O Vault não é apenas uma pasta de notas. Ele é uma das camadas do cérebro da ZARA.

## Regra central

LLM não é memória.

A memória da ZARA deve existir fora dos modelos.

## Camadas

1. Working Memory
2. Session Memory
3. Long-Term Memory
4. Semantic Memory
5. Episodic Memory
6. People Memory
7. Project Memory
8. Preference Memory
9. Procedural Memory
10. Learned Workflows

## Estrutura sugerida

```text
ZARA_VAULT/
├── 00_Inbox/
├── 01_People/
├── 02_Projects/
├── 03_Companies/
├── 04_Knowledge/
├── 05_Daily/
├── 06_Meetings/
├── 07_Conversations/
├── 08_Files/
├── 09_Web/
├── 10_Learnings/
├── 11_Workflows/
├── 12_Decisions/
├── 13_Preferences/
├── 14_Tasks/
├── 15_Automations/
├── 16_Skills/
├── 17_System/
├── 18_Research/
├── 19_Memories/
└── 99_Archive/
```

## Formato

Markdown + YAML frontmatter.

```yaml
---
id: memory_2026_09_01_001
type: person
created: 2026-09-01
updated: 2026-09-01
confidence: 0.94
source: whatsapp
privacy: private
tags:
  - pessoa
  - cliente
links:
  - "[[Projeto ABC]]"
---
```

## Pipeline de ingestão

INPUT
→ classify
→ privacy check
→ deduplicate
→ extract facts
→ summarize
→ entity link
→ confidence score
→ write markdown
→ update structured DB
→ update embeddings
→ update graph

## Fontes

- voz;
- mensagens;
- e-mails;
- arquivos;
- PDFs;
- sites;
- reuniões;
- projetos;
- código;
- tarefas;
- decisões;
- preferências;
- histórico de execução.

## Não salvar tudo cegamente

Filtros:
- relevância;
- privacidade;
- duplicação;
- retenção;
- sensibilidade;
- confiança.

## Memory Promotion

TEMPORARY
→ CANDIDATE
→ CONFIRMED
→ LONG_TERM

## Contradições

Preservar histórico:
- fato antigo;
- fato novo;
- fonte;
- data;
- confiança.

Nunca sobrescrever silenciosamente.

## Esquecimento

Suportar:
- expiração;
- arquivamento;
- “não memorize isso”;
- “esqueça isso”;
- políticas por categoria.

## Busca

Combinar:
- full text;
- metadata;
- embeddings;
- graph traversal;
- recency;
- importance;
- confidence.

## Reflection Engine

Periodicamente:
- resumir dias;
- consolidar notas;
- detectar padrões;
- relacionar pessoas/projetos;
- propor automações;
- deduplicar;
- elevar memórias relevantes.

## Arquitetura recomendada

```text
Obsidian Vault
+
Structured DB
+
Vector Index
+
Entity Graph
```

Obsidian = camada humana e portátil.
DB = estado operacional.
Vector = busca semântica.
Graph = relações.
