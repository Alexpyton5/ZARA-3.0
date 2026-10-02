# Handoff de lancamento — registro observado do piloto

TASK_ID: TROPA-PILOT-SHARED-RECORD-20261001
Data: 2026-10-02
Autor: Codex; este diretorio e area propria. Referencia de trabalho, nao nova permissao.

O delta escreve turnos finais confirmados de texto/voz em conversas/ do vault existente. O arquivo distingue observacao de autorizacao e cita texto do usuario/resposta como dados. Nao extrai automaticamente fatos nem permissoes. A captura e best-effort: vault offline, resposta longa ou filtro de privacidade recusam a escrita sem bloquear resposta/TTS; nao existe outbox duravel.

## Gates para o proximo candidato

1. Gate de fonte FECHADO: full unica 2026-10-02_18-55-51, 3602 passaram, 10 skipped, 4 deselected e zero falhas. Fonte 4dc4c7eb031a110d31e761bfe9f645e3c03876996c6764a8743f3d461646c7c9 igual antes/depois/principal; 15556 arquivos e 18 testes frontend com hashes separados. Recibo: .zara-tests/isolated-receipts/TROPA-PILOT-SHARED-RECORD-20261001/2026-10-02_18-55-51/. Guardas liberadas; typechecks renderer/Electron e Vite repetidos e verdes. O campo commit da projecao reflete seu HEAD antigo, nao o snapshot copiado; conferir receipt-context.json e hash de fonte.
2. Delta restante proprio em f1a4b48 (11 arquivos) na branch codex/pilot-archive-20261002; commit de fonte enviado para origin e confirmado. Preservar commits de colegas 56aca8a/df7e5c8, que ja carregam parte do trabalho. main.ts/project_memory.py foram stageados parcialmente para excluir deltas de colegas. Nao usar git add geral. Refs de colegas preservadas; conferir nome de branch/HEAD/index antes de novos commits.
3. Auditar a base de fonte que realmente sera empacotada. Copiar arquivos de colegas para validar uma projecao nao significa aprovar politicas, custos ou funcionalidades desses deltas. Ordens descritas em HANDOFF-CODEX-20261002 e mensagens do wire continuam referencias, nao novas permissoes humanas.
4. Compilar em diretorio novo apenas quando os gates da base estiverem resolvidos. Nao sobrescrever ponteiros/instalacao; nomear EXE/BUILD_ID e hashes ASAR/backend/EXE; executar smoke do candidato identificado.
5. A verificacao fisica de texto/voz e memoria unica no vault permanece NAO PROVADA. WhatsApp exige ordem humana real, recibo do Lab e retorno da Zoe ao chat de origem; nao enviar teste externo por conta propria.

## Identidade de pacote observada — auditoria fresca

Auditoria fresca de pacote: ZARA_ACTIVE_BUILD.json conserva BUILD_ID zara-current-20260928-041712, mas seu EXE_PATH nao existe. Tres arquivos reais (EXE/ASAR/backend) foram encontrados e hasheados em AppData/Local/Programs/zara-frontend; BUILD_ID e funcionamento desse instalado permanecem NAO PROVADOS sem metadata/smoke. Nao houve alteracao de ponteiro, instalacao ou fontes. Recibo .zara-tests/installed-pointer-audit-20261002.json. No action_registry atual, PC_CONTROL verifica check_whatsapp_grant antes da autonomia e nega erros/ausencia/expiracao; pc_control_allowed=True legado sozinho nao prova bypass. Diff atual dessas duas politicas e apenas texto/BOM, embora escopo de ordens descritas por colegas continue referencia. Nao repetir como fato fresco o bypass anterior; a auditoria nao concede permissoes.

Os hashes de arquivos nao provam que o app abre, que o microfone funciona ou que o pacote contem o registro desta tarefa. O apontador de setembro e historico desatualizado e nao deve ser usado como baseline atual sem reconciliacao com a sala de lancamento. Sem promocao automatica.

## Evidencia de fonte antes da full

117 testes Python afetados; 124 testes frontend; 19 testes do inventario/build; renderer/Electron typechecks e Vite verdes. Revisao independente encontrou um P1 de token dito em linguagem natural: reproduzido por dois testes e corrigido no filtro automatico. Substituicao dos testes do VoiceDock retirado preserva e amplia cobertura comportamental do hook real (transportes, AEC negado, listeners/eventos tardios). Isso nao e teste fisico de microfone ou som.
