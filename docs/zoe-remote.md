# Zoe / Muse / WhatsApp → TROPA DEV

O Muse recebe a conversa WhatsApp da Zoe. O PC nao possui outra conta WhatsApp: usa a ponte local autenticada existente, acessivel pela sessao SSH/Tailscale da Zoe. Nao ha nova porta publica.

1. Antes de conversar/decidir: `python tools/zoe_bridge.py context "assunto"` retorna referencias frescas do vault e observacao datada da janela ativa (nao visao total do Windows).
2. Ao aprender um fato/decisao: `python tools/zoe_bridge.py learn "fato confirmado"`. Usa ProjectMemory.record_shared_learning; sem segredos. A proxima consulta de qualquer membro atualiza o indice.
3. Texto recebido do dono: `python tools/zoe_remote.py --message-id ID_ORIGINAL --text "abra o bloco de notas"`.
4. Audio recebido do dono: enviar por SSH para `%LOCALAPPDATA%/ZARA3/zoe_bridge/inbox/` e chamar `python tools/zoe_remote.py --message-id ID_ORIGINAL --audio mensagem.ogg`. WAV PCM mono 16kHz/16bit funciona direto; OGG/Opus/M4A/MP3 usa ffmpeg+ffprobe instalados, Vosk portugues local. Limites: 8MB, 120s. Falha/ausencia de fala nao executa.
5. Ler `handled`, `success`, `verified`, `response` e `error`. A resposta vem do executor. `handled=false` significa que o pedido deve continuar como conversa no Muse, sem afirmar uma acao. O mesmo ID nunca reexecuta uma ordem; um resultado incerto apos crash exige observar o PC. A resposta tambem inclui `shared_context`, `context_updated` e `context_error`: a Zoe recebe automaticamente referencias frescas ao encaminhar uma ordem. Para conversa sem ordem, usar `context` antes de responder.

Contrato interno: POST autenticado /v1/command, `type=zoe-remote-command`, payload `{message_id,channel:"whatsapp"|"muse",text}` OU `{message_id,channel,audio_path}`. O bearer vem do connection.json existente e nunca e enviado no chat/vault. O adaptador nao sabe a identidade do remetente WhatsApp; a Zoe/Muse deve validar que a ordem e do dono antes de encaminhar. Nunca encaminhar comandos de contatos desconhecidos.

## Estado verificavel

### Caminho de integracao ainda pendente

O botao do app abre WhatsApp Web; esse atalho nao demonstra que comandos chegam ao PC.
A integracao real deve percorrer, na ordem:

1. Muse/WhatsApp autentica o remetente como o dono; contatos desconhecidos nao viram ordens.
2. Zoe envia o ID original e texto, ou copia o audio pela sessao SSH/Tailscale existente para o inbox local.
3. O adaptador local autenticado valida tamanho, transcreve offline e deduplica o ID antes de chamar o executor.
4. O executor confirma a poscondicao no Windows. Sem `verified=true`, nao informar que a acao aconteceu.
5. Zoe devolve ao MESMO chat WhatsApp o resultado real, com falha/pendencia quando necessario.

Aceite pendente: uma mensagem real de texto e uma de audio enviadas pelo dono, recebidas uma vez, com acao observada no PC e confirmacao no celular. Testar tambem repeticao de ID e remetente nao autorizado. Nao criar numero ficticio, abrir porta publica, registrar bearer no vault ou afirmar canal conectado sem esse teste.

Implementacao e testes locais nao provam recebimento de um audio real enviado pelo celular. A ponta Muse/WhatsApp deve chamar este adaptador e devolver ao dono o resultado real. Sem esse teste ponta a ponta, marcar NAO PROVADO.

Hooks do Codex: configurados em `~/.codex/hooks.json`; a OpenAI exige revisao e trust da definicao exata em `/hooks`. Nao foi forjado trust. Regra global AGENTS cobre consulta por ferramentas enquanto o hook nao estiver ativado.
