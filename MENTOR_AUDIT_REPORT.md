# ZARA 3.0 — Auditoria integral e reconstrução CLEAN-002

Data: 2026-08-07
Build ID: `ZARA-3.0-ROOT-CLEAN-002`

## 1. Material auditado

A reconstrução foi feita a partir das seis partes independentes fornecidas pelo Hermes:

- `ZARA-PART-01-ROOT.zip`
- `ZARA-PART-02-CORE.zip`
- `ZARA-PART-03-MEMORY-INTEGRATIONS.zip`
- `ZARA-PART-04-CONFIG-ASSETS.zip`
- `ZARA-PART-05-FRONTENDS-A.zip`
- `ZARA-PART-06-FRONTENDS-B.zip`

Todos os ZIPs foram abertos e tiveram a integridade estrutural verificada antes da análise.

## 2. Estado encontrado

Foram encontradas seis variantes de frontend concorrentes:

1. `frontend`
2. `frontend_OLD_RENAME6`
3. `frontend_V2_STAGE`
4. `frontend_backup_20260807_010703/frontend`
5. `frontend_backup_20260807_023412`
6. `frontend_v2`

A `frontend` corrente continha os erros TypeScript antigos (`webkitAppRegion` e símbolos não usados). A V2 corrigia esses erros, porém não continha a configuração necessária de base relativa do Vite.

## 3. Causa confirmada da tela preta

O artefato real de `frontend_V2_STAGE/dist-frontend/index.html` continha:

```html
<script ... src="/assets/...js"></script>
<link ... href="/assets/...css">
```

O Electron empacotado carrega o renderer por `file://`. Caminhos iniciados em `/assets/` não apontam para a pasta `dist-frontend/assets` do aplicativo. O JavaScript/CSS do renderer deixa de carregar e a janela pode aparecer completamente preta.

Um build anterior que funcionava usava `./assets/...` e sua fonte possuía:

```ts
base: './'
```

A raiz CLEAN-002 usa `base: './'`, favicon relativo e mantém `dist-frontend` como saída única do renderer.

## 4. Frontend canônico CLEAN-002

A raiz operacional agora contém **uma única** pasta `frontend`.

Foi preservado o layout ZARA V2 aprovado, com:

- núcleo central de ~4.100 micropartículas Three.js;
- pulso idle;
- reação aos estados LISTENING e SPEAKING por nível de áudio;
- fallback CSS caso WebGL não esteja disponível;
- campo de mensagem;
- log de conversa com scroll;
- chave Supercérebro;
- ZARA Core;
- Hermes Lab;
- três agentes exibidos honestamente como pendentes;
- Memory Galaxy exibida como integração Obsidian pendente;
- apenas um conjunto de controles da janela.

Também foram removidos módulos React antigos/inativos que não faziam parte do renderer canônico.

## 5. Robustez do Electron

`frontend/src/main.ts` foi consolidado para:

- criar a janela **antes** de aguardar o backend Python;
- manter a interface visível mesmo se o sidecar estiver offline;
- usar o caminho de desenvolvimento correto para `../main.py`;
- usar `resources/backend/zara-backend.exe` em produção;
- reconhecer readiness somente pela linha exata `SYS: Interface neural pronta`;
- registrar falhas de renderer (`did-fail-load`, crash e console errors);
- mostrar uma página de diagnóstico se o renderer não puder ser carregado;
- manter um fallback HTML de boot visível até o módulo React carregar, evitando uma janela totalmente preta mesmo se o bundle falhar antes do mount;
- usar um único conjunto de handlers IPC e controles da janela;
- incluir o ícone em `resources/assets/zara.ico`;
- permitir até 5 minutos para a primeira ativação explícita da voz, pois o modelo Vosk pode precisar ser baixado/carregado.

## 6. Backend Python

Foram consolidados/corrigidos:

- `MemoryManager` assíncrono compatível com o contrato IPC;
- conversas episódicas separadas da memória compacta de fatos;
- readiness real: falhas essenciais impedem o sinal de pronto;
- registro das actions mesmo com Hermes offline;
- eventos tipados `state-change`, `voice-level`, `metrics`, `message` e `supercerebro-change`;
- Supercérebro só fica ON após confirmação real do Hermes Gateway;
- roteamento via Hermes somente quando o Supercérebro estiver realmente ativo;
- remoção da duplicação de resposta no chat de texto;
- captura de nível real do microfone para as partículas;
- loop stdin do Windows não bloqueia mais o event loop assíncrono;
- STT Vosk e TTS Kokoro preparados de forma lazy, sem carregar/baixar modelos na inicialização da ZARA;
- primeira inicialização pesada de STT é feita fora do event loop;
- dados, memória e logs do app empacotado usam diretório gravável do usuário (`LOCALAPPDATA/ZARA3`).

## 7. Limpeza arquitetural

A raiz canônica removeu do caminho operacional:

- múltiplas `frontend*` concorrentes;
- Tauri e seus scripts/dependências;
- bridge React duplicada/inativa;
- UI Flet legada (`galaxy_view.py`, `quota_panel.py`);
- `zara_launcher.py` legado;
- dependências frontend não usadas (D3, GSAP, Zustand e Tauri);
- fontes Google remotas desnecessárias;
- dados de build antigos, `node_modules`, caches e executáveis antigos.

`postcss.config.js` e `tailwind.config.js` foram deixados no formato CommonJS coerente com o pacote atual.

## 8. Segredos

O arquivo real `config/api_keys.json` **não** foi incluído na distribuição CLEAN-002.

Somente `config/api_keys.example.json` está presente. Na instalação de teste, as chaves locais existentes devem ser copiadas pelo Hermes sem imprimir seu conteúdo no chat.

## 9. Validações executadas no ambiente do Mentor

- integridade das seis partes: OK;
- `python -m compileall`: OK;
- inicialização real de `IPCHandler`: OK;
- Orchestrator: OK;
- MemoryManager: OK;
- registro das actions: OK;
- Hermes ausente tratado como integração opcional: OK;
- STT preparado lazy: OK;
- TTS preparado lazy: OK;
- emissão tipada de `state-change`, `voice-level` e `supercerebro-change`: OK;
- smoke test de `MemoryManager.add_conversation`: OK;
- parse sintático dos arquivos TS/TSX ativos: 0 erros sintáticos;
- `package-lock.json` regenerado/coerente com o `package.json` CLEAN-002.

O build TypeScript/Electron completo não é certificado neste ambiente porque as dependências npm nativas do projeto não estão instaladas aqui. O teste definitivo é `npm run typecheck` + builds no Windows do Alex.

## 10. Funcionalidades intencionalmente pendentes

Estas funções **não são apresentadas como concluídas**:

1. Galaxy conectada a um vault Obsidian externo real. O bridge atual é apenas uma estrutura local compatível/precursora.
2. Os três agentes Hermes 24/7 de Aparência, Inteligência e Funcionalidade com fila de propostas e workflow de aprovação/rejeição do Alex.
3. Política central completa de confirmação/auditoria para execução autônoma de actions de alto risco.
4. Remoção do workaround temporário `signAndEditExecutable: false` e assinatura final para distribuição.

Esses módulos devem ser construídos depois que CLEAN-002 passar no teste real de abertura/renderer/backend.

## 11. Critério de promoção

A raiz CLEAN-002 somente deve substituir a instalação operacional depois de passar, no Windows do Alex:

1. `npm run typecheck`;
2. `npm run build:electron`;
3. `python build_exe.py`;
4. `npm run build` e verificação de `./assets/` no `dist-frontend/index.html`;
5. `npm run electron:build`;
6. execução do `release/win-unpacked/ZARA 3.0.exe`;
7. screenshot comprovando renderer visível e ausência de tela preta;
8. teste controlado de backend, Supercérebro e voz.

Até essa evidência, a raiz antiga deve permanecer intacta como rollback.
