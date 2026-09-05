# Protocolo obrigatório: AUDIT FIRST

## Objetivo

Antes de expandir a ZARA, compreender integralmente a implementação existente.

## 1. Inventário total da raiz

Percorrer recursivamente a pasta raiz e registrar:
- frontend;
- Electron main;
- preload;
- renderer;
- rotas;
- estado;
- serviços;
- integrações;
- memória;
- voz;
- automações;
- banco;
- APIs;
- IPC;
- configurações;
- scripts;
- instalador;
- build;
- assets;
- protótipos;
- testes;
- logs;
- dependências;
- código morto;
- duplicações.

## 2. Mapas obrigatórios

Criar:
- árvore de diretórios;
- mapa arquitetural;
- mapa de dependências;
- mapa de IPC;
- mapa de eventos;
- mapa de estado;
- mapa de persistência;
- mapa de integrações;
- mapa de permissões.

## 3. Classificação

KEEP: bom e funcional.

CONNECT: já existe e deve ser conectado ao novo ecossistema.

REFACTOR: funciona, mas precisa organização.

REPLACE: arquitetura inadequada; substituir com plano.

DEPRECATED: legado sem função futura.

UNKNOWN: ainda não compreendido. Não tocar.

## 4. Dívida técnica

Identificar:
- duplicação;
- acoplamento excessivo;
- imports circulares;
- dependências abandonadas;
- segredos no código;
- Node exposto ao renderer;
- permissões excessivas;
- rotas mortas;
- fake data;
- mocks em produção;
- assets duplicados;
- telas concorrentes.

## 5. Regra de remoção

Não apagar nesta fase.

Criar `REMOVAL_CANDIDATES.md` com:
- caminho;
- motivo;
- dependentes;
- substituto;
- risco;
- teste;
- aprovação pendente.

## 6. Preparação

Após auditoria:
- normalizar dependências;
- corrigir scripts;
- alinhar Node/Electron;
- lint/test/build;
- corrigir preload/IPC;
- organizar env;
- garantir build limpo;
- garantir execução atual.

## 7. Transformação

AUDIT
→ MAP
→ CLEAN SAFELY
→ STABILIZE
→ REBUILD/EXPAND
→ CONNECT
→ TEST
→ BUILD
→ INSTALLER
→ REGRESSION
