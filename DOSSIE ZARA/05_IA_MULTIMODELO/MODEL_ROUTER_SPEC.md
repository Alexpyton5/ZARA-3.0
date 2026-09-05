# Model Router

## Princípio

A ZARA é model-agnostic.

Suportar:
- modelos locais;
- modelos gratuitos;
- cloud barato;
- modelos premium;
- endpoints customizados.

## Modos

- LOCAL_ONLY
- FREE
- HYBRID
- BALANCED
- PERFORMANCE
- MAX_INTELLIGENCE

## Critérios

- capability;
- cost;
- latency;
- privacy;
- context length;
- reasoning;
- vision;
- coding;
- availability;
- user preference;
- hardware.

## Política

Use o modelo mais barato e privado que resolva a tarefa com confiabilidade suficiente.

## Escalonamento

local pequeno
→ local maior
→ gratuito
→ premium

## Provider abstraction

```text
AIProvider
├── generate
├── stream
├── embed
├── vision
├── transcribe
├── synthesize
└── capabilities
```

## Runtimes locais

Arquitetura compatível com:
- Ollama;
- llama.cpp;
- MLX;
- vLLM;
- endpoints OpenAI-compatible.

## Hardware awareness

Detectar:
- CPU;
- RAM;
- GPU;
- VRAM;
- arquitetura;
- disco.

## Budget

Usuário define:
- zero;
- limite mensal;
- limite diário;
- limite por tarefa.

## Privacy Router

Categorias privadas podem ser proibidas de usar cloud.

## Multi-model reasoning

Tarefas complexas podem usar:
- planner;
- coder;
- vision;
- verifier.
