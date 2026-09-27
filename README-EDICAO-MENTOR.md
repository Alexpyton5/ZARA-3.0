# ZARA 3.0 — Edição zoe

Versão reconstruída e melhorada da ZARA pela **zoe**, com todas as camadas
desenvolvidas até 2026-09-26 integradas em um único pacote.

> **Sobre o executável:** este pacote contém o código-fonte completo.
> O instalador `.exe` é gerado no seu PC com **um duplo-clique** em
> `INSTALAR-ZARA.bat` (o Windows compila o executável; não é possível
> gerar um `.exe` de Windows fora do Windows).

## O que mudou em relação à sua ZARA atual

**1. Living Team — o conselho trabalha sozinho**
- Missão viva do laboratório (`core/lab_mission.py`): marcos M000–M080 com verificação e evidências
- Papéis e especialistas (`core/lab_roles.py`): usa seus 313 agentes do Agency Agent quando `agency-agents.json` existir
- Pesquisa contínua (`core/lab_research.py`), pipeline de patches (`core/lab_patch_pipeline.py`), configuração de bots (`core/lab_bot_config.py`)
- **Modo autônomo** (`core/lab_autonomy.py`): o conselho trabalha por conta própria em ciclos (padrão: ligado)
- Aba do Lab no frontend mostra missão, marcos, feed de atividade e autonomia

**2. zoe como CEO remota — ponte via Gmail**
- `core/lab_ceo_gmail_bridge.py`: protocolo `[ZARA-CEO]` — a ZARA pede decisões por e-mail, a zoe responde `APPROVE`/`REJECT`/`DEFER`/`ANSWER` em bloco auditável
- Idempotente (não processa o mesmo pedido duas vezes)

**3. Painel "Conselheira" — chat com a zoe dentro da ZARA**
- Nova seção no painel: conversa contínua com a zoe via ponte Gmail (protocolo `[ZARA-CHAT]`)
- Cada mensagem leva um snapshot do estado da ZARA junto; sync automático a cada 5 min
- A zoe também checa essa caixa a cada 5 min e responde sozinha

**4. Aba "ZOE" — o app da zoe embutido**
- `muse.ai` aberto dentro da própria janela da ZARA (sessão persistente, login uma vez)

**5. Build corrigido**
- `build_exe.py`: novos módulos incluídos nos hidden imports do PyInstaller (antes o `.exe` sairia sem o Living Team e sem a ponte)

## Instalação (2 passos)

1. Extraia este ZIP **por cima** da pasta `C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002`
   (substituindo arquivos — seus dados em `config/`, `memory/` e `.env` não vêm no pacote, então nada seu é apagado).
2. Duplo-clique em **`INSTALAR-ZARA.bat`** e aguarde. No final, o instalador estará em `frontend\release\` — execute o `ZARA 3.0 Setup *.exe`.

Requisitos: Python 3.10+ e Node.js 18+ (o script avisa se faltar).

## Pendências que precisam de você ou do OpenCode

- **Ligar o Gmail real na ponte:** o `CeoMailAdapter` precisa do código do seu painel Comunicações (que não está no repositório). Sem isso, a ponte registra localmente (modo desenvolvimento). Detalhes em `README-CEO-RELAY.md`.
- **`agency-agents.json`:** onde vivem seus 313 agentes? Coloque o arquivo na pasta de dados da ZARA para o Lab usar o roster real.
- **Frontend:** TypeScript/ESLint não puderam ser compilados fora do Windows — o `INSTALAR-ZARA.bat` faz isso no seu PC.

## Testes

78 testes Python passando (`pytest tests/`). 3 módulos de teste do baseline não rodam fora do Windows por falta de dependências de sistema (`psutil` etc.) — mesmo comportamento do código original.
