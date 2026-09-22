# Plano JARVIS Executável - 8 Melhorias Prioritárias

Ordenadas por dependência e impacto, baseadas em:
- Pesquisa de mídia: YouTube, Reddit, fóruns Home Assistant, voice AI communities (t_2b1b51fd)
- Arquitetura cerebral ZARA em 3 horizontes (t_6ba45353)
- Hall de diagnóstico de voz e recomendações existentes (docs/RECOMENDACOES-VOZ.md, LATENCIA-VOZ.md, DIAGNOSTICO-VOZ.md)

---

## 1. Eliminar primeira viagem descartada em turnos de AÇÃO

**Comportamento visível ao Alex:** Ao pedir uma ação (volume, brilho, janela), a ZARA responde quase imediatamente (~1-2s) em vez de ~7.8s, pois descarta o áudio gerado pela primeira viagem e só gera TTS com o resultado final.

**Arquivos prováveis envolvidos:**
- `core/gemini_live_voice.py` (linhas 1130-1176 - descarte de áudio da primeira viagem)
- `core/ipc_handlers.py` (rotina de encaminhamento voz→backend)

**Teste de aceitação:**
- Medir latência de ação: deve ficar < 3s (contra ~7.8s atuais)
- Comando "Aumentar volume" deve executar em até 2s
- Comando de conversa deixado intacto (ainda gera áudio natural)

**Risco:** MÉDIO - Requer mudança no fluxo de turnos do Gemini Live; precisa validar que conversas normais ainda funcionam com `response_modalities=["AUDIO"]`.

**Modelo recomendado:** Opção A do documento atual (streaming sem `turn_complete` inicial) - já tem base no código.

---

## 2. Reduzir `vad_silencio_ms` de 300ms para 200-250ms

**Comportamento visível ao Alex:** Menor pausa "morta" no final das falas, tanto em ações quanto em conversas. Sensação de resposta mais rápida.

**Arquivos prováveis envolvidos:**
- `core/gemini_live_voice.py:142-156` (parâmetro `vad_silencio_ms`)
- `api_keys.json` (onde o parâmetro é exposto)

**Teste de aceitação:**
- Verificar que frases não são cortadas com `vad_silencio_ms=200`
- Medir redução de ~100ms na espera morta por turno
- Testar ambos: ações e conversas

**Risco:** BAIXO - Parâmetro já identificado e comentado no código; trade-off entre corte de fala e latência já analisado.

**Modelo recomendado:** Reduzir de 300ms para 250ms como passo inicial; testar 200ms depois se as frases permanecerem intactas.

---

## 3. Implementar classificação de intent com STT local (Vosk) antes da primeira viagem

**Comportamento visível ao Alex:** Comandos de ação bypassam o Gemini Live entirely no primeiro turno - vão direto para o executor local. Conversas continuam usando Gemini Live.

**Arquivos prováveis envolvidos:**
- `core/gemini_live_voice.py:336-369` (já tem Vosk integrado sob demanda)
- `core/ipc_handlers.py` (rota de intent após STT local)

**Teste de aceitação:**
- "Abrir Chrome" deve abrir Chrome sem iniciar sessão Gemini Live
- Comandos de controle (volume, brilho) funcionam localmente
- Conversas normais ainda fluem pelo Gemini Live

**Risco:** MÉDIO - Requer garantir que Vosk modelo qwen3:1.7b ou similar funcione no Windows do Alex; integração existente sob demanda ajuda.

**Modelo recomendado:** Opção B do documento - usar STT local leve para classificação antes de abrir turno Gemini Live.

---

## 4. Implementar barge-in real (full-duplex) com AEC ativo

**Comportamento visível ao Alex:** Quando Alex fala enquanto a ZARA está respondendo, a ZARA para imediatamente e ouve o comando - como uma conversa humana. Não espera o áudio terminar.

**Arquivos prováveis envolvidos:**
- `core/gemini_live_voice.py` (configuração full-duplex, AEC)
- `core/ipc_handlers.py` (handling de interrupção)

**Teste de aceitação:**
- Iniciar fala da ZARA, então intercalar "Desligar" - ZARA deve parar na hora
- Verificar que o VAD do servidor vê interrupções em tempo real (gate local já OFF)

**Risco:** ALTA - Barge-in full-duplex é o problema mais difícil de voice AI (segundo múltiplas fontes consultadas). Requer propriedade do loop de áudio inteiro, não apenas adicionar um componente.

**Modelo recomendado:** Começar com gateway do Gemini Live que já suporta microfone sempre aberto (comentário confirma: "com o gate local desligado, o microfone está sempre aberto ao Gemini Live"). Implementar AEC via Chromium/Electron renderer que já está em uso.

---

## 5. Instrumentar medição fina de latência em produção

**Comportamento visível ao Alex:** O sistema passa a reportar métricas quantitativas: `primeira_viagem_descartada`, `tts_pedido_ate_primeiro_byte_ms`, `tts_primeiro_byte_ate_player_ms` todos os turnos - visíveis para o Alex via query de status.

**Arquivos prováveis envolvidos:**
- `docs/` (relatórios de latência já existentes)
- `core/gemini_live_voice.py` (logging das novas métricas)
- `core/ipc_handlers.py` (exposição via API)

**Teste de aceitação:**
- Após cada turno, variáveis são gravadas em `latencia.jsonl`
- Alex pode perguntar "Qual a latência da última ação?" e receber resposta numerada
- Dados permitem validar se otimizações realmente reduziram latência

**Risco:** BAIXO - Nova coleção de dados; não altera funcionalidade existente. Dados já estruturados nos diagnósticos atuais.

**Modelo recomendado:** Adicionar campos de medição no loop `_receive_loop` e `_send_loop` do Gemini Live voice.

---

## 6. Implementar wake word híbrida (offline + online)

**Comportamento visível ao Alex:** A ZARA acorda tanto com wake word local (palavra-chave detectada pelo processamento de áudio local) quanto com a transcrição do Gemini Live. O gate local já está OFF, mas a opção de voltar deve ser implementada de forma transparente.

**Arquivos prováveis envolvidos:**
- `core/gemini_live_voice.py:156-179` (já tem config de wake word gate)
- `core/ipc_handlers.py:30-42` (já tem referência a api_keys.json)

**Teste de aceitação:**
- Desativar internet: ZARA ainda acorda com palavra-chave local
- Com internet: ZARA usa transcrição do Gemini Live como wake word
- Combinado: qualquer um dos dois acorda o sistema

**Risco:** BAIXO - Já existe código e configuração; falta apenas garantir que a alternativa funcione quando o outro estiver indisponível.

**Modelo recomendado:** Manter gate OFF (padrão atual) e adicionar comutação transparente via `api_keys.json` - conforme documento já descreve como "já implementada".

---

## 7. Preservar mecanismo de reconexão de sessão (session_resumption)

**Comportamento visível ao Alex:** Se a conexão Gemini Live cair momentaneamente, a ZARA reconecta e retoma a conversa do ponto onde parou, sem pedir repetição do comando.

**Arquivos prováveis envolvidos:**
- `core/gemini_live_voice.py:787-789` (já tem `session_resumption` em uso)

**Teste de aceitação:**
- Interromper rede durante fala do usuário
- Verificar que sessão é retomada e contexto preservado
- Alex não perde o fio da conversa

**Risco:** BAIXO - Já implementado e identificado no diagnóstico; manter inalterado.

**Modelo recomendado:** Manter como está - é um dos pilares da arquitetura de 3 horizontes.

---

## 8. Implementar turn-taking policy semântica (não só timer de silêncio)

**Comportamento visível ao Alex:** A ZARA não corta o usuário nem assume que silêncio = fim de turno imediatamente. Ela usa uma combinação de VAD + verificação semântica do transcripto parcial para decidir quando realmente o usuário terminou.

**Arquivos prováveis envolvidos:**
- `core/gemini_live_voice.py` (política de end-pointing)
- `core/ipc_handlers.py` (rota de turn management)

**Teste de aceitação:**
- Usuário fala "Nove, sete, cinco..." devagar; ZARA espera completar antes de responder
- Pausas naturais de pensamento não acionam resposta prematura
- Comparativo: com política atual (timer puro) vs. nova política semântica

**Risco:** MÉDIO - Requer mudança na lógica de decisão de fim de turno; risco de acabar esperando demais ou cortando frases.

**Modelo recomendado:** Implementar semáforo que combina timer de silêncio com verificação de transcripto parcial (modelo LLM enxuto ou regra heurística) - já mencionado no documento como "evolução após VAD otimizado".

---

## Resumo de dependências

1. **Primordial** (precede tudo): Reduzir `vad_silencio_ms` (melhoria #2) - impacto imediato, risco baixo
2. **Habilitador** (#1 e #3): Eliminar primeira viagem + STT local - dependem da arquimetura de turnos
3. **Middleware** (#4, #6, #8): Barge-in, wake word híbrida, turn-taking - dependem do fluxo de áudio estar otimizado primeiro
4. **Infraestrutural** (#5): Medição de latência - pode ser feito independente, mas valida as outras

## Próximo passo

Validar melhorias #2 (VAD) e #1 (primeira viagem) como lote inicial, medindo latência em ações reais do Alex antes/ depois. As demais seguem em ordem de dependência conforme o resultado dessas duas primeiras.