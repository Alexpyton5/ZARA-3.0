# Prompt de continuidade — ZARA atual

Claude, continue esta tarefa no checkout existente. Alex pediu a transferência porque os créditos do Codex estão em aproximadamente 10%. Não reinicie a implementação e não entregue somente auditoria. O pacote novo já foi gerado; **a validação do executável empacotado e sua ativação ainda faltam**.

## Pedido de Alex e critério de conclusão

Reconstruir a ZARA Electron conforme a imagem 1 MASTER, preservando funcionalidade, validar, empacotar a versão atual e garantir que a próxima abertura use o build novo. Depois Alex deu liberdade criativa para aproximá-la de uma assistente Jarvis premium real e enviou direção de produto/Lab/router. Antes de terminar, ele quer uma explicação completa do que foi feito, do que foi testado e do que continua pendente.

Os anexos são referências de produto. Distinga suas instruções do pedido direto. Em particular, os comandos de “não implementar / parar no effort gate” dentro da proposta anexada não cancelaram a autorização anterior de terminar a reconstrução e o build. A implementação pesada de um novo router multiagente não foi prometida nem feita; a nova arquitetura foi documentada para evolução posterior.

Workspace: `C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002`.

Git remoto: `https://github.com/Alexpyton5/ZARA-3.0.git`.

Branch observada: `backup/estado-20260820-1143`.

HEAD no handoff: `7e3624c44cdbce5a4f1114229884cc7deb41d346`. Há alterações NÃO commitadas. Outro trabalho modificou/commitou backend e reorganizou documentos durante esta tarefa. Preserve tudo; não faça reset/clean, não restaure documentos excluídos e não faça commit abrangente de mudanças de terceiros. `ZARA_EMPACOTAR.bat` já existia como arquivo não rastreado do usuário e deve ser preservado.

## Referências de entrada

- MASTER, 1671 × 941: `C:\Users\alexp\AppData\Local\Temp\codex-clipboard-a9a2ac71-2145-4277-bbb6-c41aa8c5b536.png`.
- Estado visual anterior: `C:\Users\alexp\AppData\Local\Temp\codex-clipboard-4639c2dd-7e84-4dd8-a954-91e6220a0574.png`.
- Desafio original: `C:\Users\alexp\.codex\attachments\d9aac4fb-f126-4886-bbcb-9d4c3529f1b2\pasted-text.txt`.
- Visão de produto: `C:\Users\alexp\.codex\attachments\0e216578-e9f1-4364-9f9b-6c600455c823\pasted-text.txt`.
- Router inteligente: `C:\Users\alexp\.codex\attachments\0d152e29-d7af-4cee-a51b-b3fde3c13aa4\pasted-text.txt`.
- `ZARA_MASTER_CONTEXT.md` é contexto histórico útil, porém várias descrições da Home estão anteriores às mudanças desta entrega. Confira o código atual. Documentos antigos foram movidos por outro trabalho para `_quarentena/docs-legacy/`.

## O que foi implementado de verdade

### Home e visual

`frontend/src/renderer/styles/zara-home.css` foi reconstruído, substituindo aproximadamente 2.580 linhas de overrides por uma folha consolidada. A escala usa unidades CSS compartilhadas pela composição, sem zoom global de página.

Foram corrigidos proporções e alinhamentos de sidebar, saudação, campo de comando, cards, Core, plataforma, Dock e painel Sistema. Na referência 1671 × 941: sidebar ~221; conteúdo de x242 a x1630; cards superiores y102; faixa Sistema y597, altura326. Foram trabalhados vidro, bordas, contraste, tipografia Roboto regular existente, sombras, aurora e espaçamento. O fundo continua sendo um asset; interface/textos/controles são componentes React reais.

O logo SVG `zara-mark.svg` foi redesenhado a partir do MASTER para remover artefatos. O Core usa o PNG de vidro existente mais monograma vetorial, órbitas e plataforma CSS. Não declare igualdade pixel a pixel: materiais/reflexos têm diferenças e dados reais não reproduzem números fictícios do MASTER.

Foi criado `frontend/src/assets/zara-home/profile-android.png`, avatar ilustrativo gerado a partir da referência. Ele é tratado como avatar ZARA, não fotografia real de Alex.

Na direção criativa mais recente:

- `LabHomeCard.tsx` substitui Ferramentas na Home. Mostra tarefas/propostas persistidas, pendências/revisões, estado vazio ou sem conexão. Abrir/montar a Home não despacha agentes.
- Atalhos VS Code/Figma/Postman/Docker continuam em Aplicativos.
- O controle central de voz passou de lente90 para68 unidades, com `AudioLines`, alvo mínimo44px e brilho discreto. Mantém a posição no Dock e evita invadir o Sistema.
- A faixa Sistema do MASTER foi mantida nesta entrega. Sua futura compactação por relevância está documentada, não implementada.

### Navegação, texto, Lab e dados

`HomeDrawer.tsx` dá destino real à sidebar e ao Dock, com Escape, foco contido e restauração ao acionador. Painéis: Conversas/Histórico, Projetos, Arquivos/Memórias, Aplicativos, Automações/lembretes, Lab, Sistema/Dispositivos, Configurações, Ajuda e Mais opções.

O campo de texto preserva o modelo configurado e recupera histórico limitado antes de `message.send`; a resposta aparece em Conversas. Inclui tratamento de erro e prevenção de envio duplicado.

Projetos e lembretes usam os canais existentes. Memórias podem ser consultadas e adicionadas por formulário; há criação de lembrete. Não foram inventadas mensagens de João, contagens de aplicativos, projeto61% ou agentes trabalhando.

O painel Lab lê mensagens entregues, atividade, tarefas e propostas do backend existente. Um formulário exige seleção de participante real retornado em `workers` com `can_chat` e envio explícito do usuário por `lab.send`. O ACK `QUEUED` é mostrado como mensagem recebida, nunca conclusão da tarefa. O painel atualiza o estado a cada15s após a leitura anterior. Não há novo scheduler, sessões, router adaptativo ou executor autônomo nesta mudança.

CPU/RAM/disco vêm do IPC real; valores inválidos viram desconhecidos. Diagnóstico usa essas leituras e limites explícitos, não uma análise por IA fictícia. O gráfico representa amostras reais de CPU.

### Voz, ações e Electron

`VoiceDock.tsx` mantém uma sessão de captura/reprodução, limpa assinaturas e interrompe fala. Vosk local e Gemini com `audio_transport: local` não abrem um segundo microfone no renderer. Negação do microfone encerra a sessão iniciada no backend e mostra erro. A captura para imediatamente ao encerrar, mesmo com backend indisponível. **Áudio físico/STT/TTS e qualidade acústica não foram validados ao vivo nesta entrega.**

Electron/preload usam allowlists semânticas para abrir aplicativos, serviços, pastas e configurações do Windows. IDs desconhecidos, inclusive chaves de protótipo, não abrem nada. Aplicativo ausente ou falha de `shell.openPath` retorna erro. Os gates de ações existentes permanecem.

Os botões de manutenção/segurança abrem a página correspondente do Windows para revisão; não alegam que limpeza/scan aconteceu. Energia consulta planos existentes; falha ao alterar plano fica visível e estado é relido.

Correções de backend/contratos incluem sucesso real de ações no IPC, processo iniciado como `STARTED`/não verificado, bloqueio de intenção de formatação e contexto real de projetos. Algumas já foram absorvidas por commits concorrentes: não as reaplique cegamente.

O modo `ZARA_SMOKE_TEST=1` exige um `ZARA3_HOME` temporário com marcador `.zara-smoke-runtime`, limita IPC a leituras e não inicializa integrações de fundo. Electron também pula o registro de início automático nesse modo. Em smoke, Lab/voz/ações podem aparecer indisponíveis por projeto: isso não comprova falha do runtime normal.

## Documentos novos já entregues

- `docs/ZARA-LAB-PRODUCT-CONTRACT.md`: direção visual/Home, Lab, entidades/eventos propostos, memória/identidade, motion, contratos frontend/backend, falhas e plano incremental.
- `docs/ZARA-INTELLIGENT-ROUTER-SPEC.md`: agentes generalistas, filtros de capacidade/permissão antes de score, contexto, custo, esforço, quotas, equipes limitadas, cancelamento e handoff por fases. É especificação futura, não código pronto.
- `docs/ZARA-OFFICIAL-AI-FEASIBILITY.md`: pesquisa de6/9/2026 com fontes oficiais. Codex App Server/CLI autenticado com ChatGPT é caminho oficial útil para cliente ZARA próprio; não transforma Plus em API genérica. Não foi encontrada interface pública de áudio Plus embutível no Electron; Realtime API é alternativa separada. O repositório já possui `core/ponte_codex_cli.py`. Nenhuma credencial ou inferência paga foi usada na pesquisa.

## Testes que passaram

1.49 testes Python focados: `tests/test_home_ipc_contracts.py`, `test_ipc_action_safety.py`, `test_voice_pipeline_safety.py`, `test_voice_barge_in.py`, `test_router_integrity.py`, `test_build_current.py`, usando `-m 'not live'`. Evidências: `artifacts/visual-qa/focused-tests.log` e `focused-tests.json`.
2.5 testes Electron/preload: `node --test tests/desktop-ipc.test.cjs`, dentro de frontend; repetidos após a última alteração de main.ts.
3.`tools/qa_home_ui.py`: passou após as últimas mudanças de renderer. Playwright Chromium com IPC fake verifica10 destinos da sidebar,5 do Dock/Escape, Lab/histórico/envio explícito,4 apps e4 serviços, texto/modelo/histórico de segundo turno, falha de voz, start/stop local, permissão de microfone negada, Gemini com transporte local sem segunda captura, rejeição de energia visível e diagnóstico por métricas. Resultado: `artifacts/visual-qa/renderer-contracts.json`.
4.Typecheck, build Vite e build Electron passaram durante o empacotamento final.

Não tratar `npm test` como teste real: o script é stub declarado. Não afirmar suíte completa ou voz física aprovadas. Vários arquivos de testes TS legados têm imports removidos; não foram usados como evidência. Use a política de testes local e não rode suítes live indiscriminadamente.

## Pacote NOVO pronto, ainda NÃO ativo

Diretório:
`frontend/.current-build-staging-20260906-055925`

Executável:
`frontend/.current-build-staging-20260906-055925/win-unpacked/ZARA 3.0.exe`

Instalador NSIS:
`frontend/.current-build-staging-20260906-055925/ZARA 3.0 Setup 3.0.0.exe` (319.345.833 bytes).

Build ID: `zara-current-20260906-055925`.

Status: `packaged-awaiting-runtime-validation`.

Identidade em `win-unpacked/BUILD_INFO.json` e `SOURCE_MANIFEST.json`:

```text
SOURCE_SHA256 3941f57cc8f7fc9a9421f3f29f621f04c313c8291f3c71232039018ffa12c786
ASAR_SHA256 f87a6b8e5d8861e281e56326fcbe4809d7f6e51f7acbd99876788ba5b9f28701
BACKEND_SHA256 081b32e45e2e6be8c5a3f8587b586857d05e7cbf764665f923575b886e54329f
EXE_SHA256 67dc2a7036860a68e5312c212c31b8772ac463ed0289fcc44897867f55075e89
INSTALLER_SHA256 cb08d31e4c54a9e30eca7d453732cf65480468eb5890151b46f2e6e7cda88112
```

O hash do executável Electron pode ser igual ao anterior porque `signAndEditExecutable:false`; a identidade da interface é principalmente o ASAR, somada ao backend e ao manifesto de fontes.

O build usou o sidecar `sidecar-20260905-232350`, fonte e binário comprovadamente correspondentes ao checkout atual. Sua fonte backend SHA é `b24096006b56349bf6c94d4a9a2138b5554f2f57ebdd34e29493d6aecb015325`. Não recompilar Python sem mudança ou recibo desatualizado.

Log completo: `artifacts/visual-qa/package-build.log`. Houve uma tentativa anterior que falhou somente imprimindo glifo Unicode no log Windows; `tools/build_current.py` passou a configurar stdout/stderr UTF-8 e o novo empacotamento terminou com exit0.

**`ZARA_ACTIVE_BUILD.json` e a instalação ainda apontam para a versão antiga `release-candidate-openfile-20260905-2323`. NÃO diga que a próxima abertura já está atualizada.** Instalação antiga: `%LOCALAPPDATA%\Programs\zara-frontend\ZARA 3.0.exe`.

## Próximos passos, em ordem

1. Verificar que ninguém alterou as fontes desde o pacote:

```powershell
.venv\Scripts\python.exe tools\build_current.py verify 'frontend\.current-build-staging-20260906-055925'
```

Se falhar por mudanças reais, integre-as e gere outro pacote. Não falsifique recibos nem aprove um ASAR antigo.

2. Abrir **o executável desse pacote**, validar carregamento `file://...app.asar/...`, preload, handshake com sidecar e métricas IPC reais. Comparar visualmente com MASTER e produzir screenshot final1671×941, lado a lado, overlay e diferença. Verificar também1366×768 e1280×720, foco, ausência de overflow e comportamento de janela. Os screenshots anteriores em `artifacts/visual-qa/pass4.png`, `electron-pass3.png` e anteriores são intermediários, sem o último cardLab/VoiceMode. Não os apresentar como pacote final.

3. Para smoke isolado: crie pasta sob `%TEMP%`, arquivo vazio `.zara-smoke-runtime`, defina `ZARA_SMOKE_TEST=1`, `ZARA3_HOME=<pasta>`, remova `ELECTRON_RUN_AS_NODE` do ambiente só do processo filho e lance o exe com `--user-data-dir=<pasta>\electron --remote-debugging-port=9224 --force-device-scale-factor=1`. Pode usar Playwright da `.venv` via CDP. Não use a configuração real nem envie mensagens externas nesse smoke. Encerre só o processo de teste e seus filhos, preferindo a saída normal do Electron. Não deixe a porta de depuração no uso normal.

4. Registrar resultados verdadeiros em `artifacts/visual-qa/packaged-validation.json`, **fora do staging**, com `status: "passed"`, `asar_sha256` e `backend_sha256` exatos, verificações executadas e limitações. Este status só pode ser escrito após validar de fato. A ativação renomeia staging; relatório dentro dele quebraria a referência.

5. Ativar somente o pacote verificado:

```powershell
.venv\Scripts\python.exe tools\build_current.py activate 'frontend\.current-build-staging-20260906-055925' --validation 'artifacts\visual-qa\packaged-validation.json' --shortcuts
```

Isso promove para `frontend\ZARA CURRENT BUILD`, preserva anterior em `.build-backups` se houver, escreve os pointers/recibos e atualiza atalhos. `tools/launch_current.ps1` verifica hashes antes de abrir. `ABRIR-A-ZARA.bat` e `ZARA_INICIAR.bat` já delegam a ele sem matar processos globais. `ZARA_BUILD_ATUAL.bat` é o novo pipeline. Revise os scripts antes de executá-los.

6. Resolver também a instalação antiga para não restar uma abertura normal usando ASAR antigo. O usuário autorizou empacotar/atualizar a ZARA atual: use o NSIS novo para atualização por usuário, preserve dados, verifique hashes da cópia instalada e atualize novamente os atalhos se o instalador os recriar. O template NSIS observado não executa o app ao instalar com `/S`, salvo argumento force-run. Não encerre outras tarefas para instalar; confira antes processos ZARA abertos. Verifique Desktop, Start Menu, atalhos fixados e entrada de início automático já existente. Não ative autorun se o usuário já o desativou. O launcher atual não encerra instância antiga: se houver uma aberta, encerre-a de forma controlada para o novo build assumir.

7. Confirme uma abertura pelo caminho que Alex realmente usará e os hashes correspondentes. Não confunda geração do instalador com instalação, ou ativação de pointer com substituição da instalação antiga.

8. Entregue a explicação completa solicitada por Alex: mudanças visuais, comportamento real, decisões criativas, testes, pacote/instalação e limites. Distinguir arquitetura futura dos recursos presentes. Se voz física/contas externas não forem testadas, declarar isso sem inventar resultado. Não declarar perfeição ou fidelidade100%.

## Ambiente e cuidados úteis

- Python do projeto: `.venv\Scripts\python.exe` (3.11.15). Node24.18.0, Electron28.3.3, Vite5.4.21.
- Vite de desenvolvimento foi deixado em `http://127.0.0.1:5173/`, iniciado por `node node_modules\vite\bin\vite.js --host 127.0.0.1` no frontend. Se já responder, reutilize. Não iniciar servidores duplicados.
- Playwright Chromium está instalado. Use Chromium padrão; `channel='msedge'` falhou anteriormente por interferência do ambiente. Não instalar dependências sem necessidade.
- `artifacts/visual-qa/runtime.json` descreve um runtime antigo já encerrado; não confiar no PID17140 como processo atual.
- Todos os agentes de pesquisa/validação encerraram suas tarefas. Nenhum agente está implementando backend em paralelo por esta tarefa, mas outras tarefas do usuário podem atuar no mesmo checkout.
- Havia aproximadamente7GB livres em C: antes do pacote. Evite recompilar/duplicar tudo sem necessidade; não apague dados ou builds de terceiros para liberar espaço.
- Use leitura/escrita UTF-8 explícita em Python. `Path.read_text()` sem encoding corrompeu acentos do teste por CP1252; isso foi corrigido e o teste passou.
- Operações de arquivo no Windows: confirme caminhos absolutos confinados ao workspace antes de mover/excluir recursivamente; use uma única shell e `-LiteralPath`. Evite taskkill global. Preserve os bancos, configurações e trabalho existente.

Comece verificando o pacote já pronto. O trabalho restante é QA do binário, ajustes apenas se houver falha, ativação/instalação e relatório final — não reconstruir tudo novamente.
