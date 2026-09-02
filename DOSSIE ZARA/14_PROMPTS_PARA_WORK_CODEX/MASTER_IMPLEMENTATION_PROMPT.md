# Prompt mestre para construção da nova ZARA

Você está assumindo a evolução de um projeto existente chamado ZARA.

NÃO comece implementando features novas.

## FASE A — AUDITORIA OBRIGATÓRIA

Leia primeiro todo o `DOSSIE ZARA`.

Depois percorra recursivamente a raiz do projeto real.

Leia e mapeie:
- Electron main;
- preload;
- renderer;
- frontend;
- componentes;
- rotas;
- estado;
- serviços;
- integrações;
- voz;
- memória;
- automações;
- IA;
- banco;
- APIs;
- IPC;
- build;
- installer;
- testes;
- assets;
- scripts;
- documentação;
- legado.

Não altere nada até produzir relatório confiável.

Classifique:
KEEP
CONNECT
REFACTOR
REPLACE
DEPRECATED
UNKNOWN

Não delete. Liste candidatos em `REMOVAL_CANDIDATES.md`.

## FASE B — ESTABILIZAÇÃO

Depois:
- corrigir build;
- normalizar dependências;
- organizar scripts;
- corrigir riscos arquiteturais;
- garantir contextIsolation;
- manter nodeIntegration false;
- centralizar IPC;
- estabelecer testes mínimos;
- validar app atual.

## FASE C — TRANSFORMAÇÃO

Transformar a aplicação atual no novo ecossistema.

Regra de ouro:
A ZARA não é um chatbot.
É uma entidade operacional que permite usar o computador por intenção e voz.

Implementar em camadas:
- UI;
- Brain;
- Model Router;
- Tool Router;
- Executor;
- Verifier;
- Recovery;
- Permissions;
- Platform Adapters;
- Browser Agent;
- Voice;
- Memory;
- Obsidian Vault;
- Automations;
- Skills.

## SEGUNDO CÉREBRO

Implementar Obsidian Vault como memória legível e expansível.

Nunca gravar tudo cegamente.

Usar:
- classificação;
- deduplicação;
- confiança;
- privacidade;
- retenção;
- entity linking;
- embeddings;
- structured DB;
- graph;
- reflection.

## IA

ZARA deve ser model-agnostic.

Suportar:
- local;
- gratuito;
- premium;
- híbrido.

Criar ModelRouter.

Política:
usar o modelo mais barato e privado que resolva a tarefa com confiabilidade suficiente.

## INTERFACE

MASTER Titanium Emerald é fonte visual.

Não usar screenshot em produção.

Reconstruir em componentes reais.

Overlay da MASTER somente em desenvolvimento.

## EXECUÇÃO

Toda tarefa:

OBSERVE
→ PLAN
→ ACT
→ VERIFY
→ RECOVER IF NEEDED
→ COMPLETE
→ WRITE MEMORY IF RELEVANT

Não considerar clique como sucesso.

## SEGURANÇA

Classificar ferramentas:
SAFE
CONFIRM
HIGH_RISK
BLOCKED

## ENTREGA

Trabalhar em etapas verificáveis.

Após cada fase:
1. descrever mudanças;
2. listar arquivos;
3. rodar testes;
4. rodar build;
5. explicar riscos;
6. indicar próximos passos.

Não remover legado até substituição funcional e validada.
