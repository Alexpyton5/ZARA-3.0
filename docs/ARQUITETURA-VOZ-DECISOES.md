# Decisão de Arquitetura: Eliminar a Primeira Viagem Descartada em Turnos de Ação

## Contexto
A medição de latência da ZARA (docs/LATENCIA-VOZ.md) mostra que em turnos de ação (quando o usuário pede para executar algo no PC, como "abaixa o volume"), a ZARA gasta cerca de 6,7 segundos gerando áudio do modelo (Kore lendo a resposta) apenas para descartá-lo byte a byte antes de executar a ação e iniciar a segunda viagem (TTS do resultado verificado). Esse gargalo é responsável pela maior parte da latência percebida pelo usuário em ações.

## Objetivo
Eliminar a geração de áudio desnecessária na primeira viagem de turnos de ação, mantendo:
- Conversa direta (turnos de conversa continuam áudio direto ao modelo)
- Reconexão de sessão (session resumption)
- Barge-in (o usuário pode interromper enquanto a Kore fala)
- Wake word híbrida (padrão gate OFF por transcrição)
- Nunca declarar sucesso antes de verificar a ação (regra de verdade da ZARA)

## Opções Consideradas

### Opção A – Streaming de entrada sem `turn_complete` inicial
- Envie o áudio do microfone ao Gemini Live **sem** fechar o turno (`turn_complete=False`).
- Receba a transcrição parcial/final via `input_audio_transcription`.
- Assim que houver texto suficiente, execute `_voice_can_answer_directly` (ou `_voice_turn_needs_executor`) localmente.
- Se for AÇÃO, continue recebendo áudio apenas para manter a conexão viva, mas **não processe** o áudio gerado pelo modelo (descarte‑o no `_receive_loop`).
- Quando o executor terminar, inicie a segunda viagem enviando `FALE_EXATAMENTE: <resultado>` e aguarde `turn_complete`.
- Se for CONVERSA, deixe o áudio do modelo tocar normalmente (`_play_generated_audio=True`).

**Benefício**: elimina a geração de áudio da primeira viagem (~6,7 s) em turnos de AÇÃO, preservando a pipeline de streaming para CONVERSA.

### Opção B – Classificação de intent com STT local antes da primeira viagem
- Use um modelo leve de STT local (ex.: Vosk) para transcrição imediata do áudio do microfone.
- Com a transcrição parcial, avalie `_voice_turn_needs_executor` (ou `_voice_can_answer_directly`) **antes** de enviar qualquer coisa ao Gemini Live.
- Se for AÇÃO, não abra o turno Gemini Live; encaminhe direto para o executor e, após a ação, inicie apenas a segunda viagem (TTS) com `FALE_EXATAMENTE:`.
- Se for CONVERSA, proceeda normalmente com a conexão Gemini Live.

**Benefício**: evita completamente a primeira viagem em AÇÃO, reduzindo latência para o tempo do STT local + executor + segunda viagem.

### Opção C – Primeiro turno apenas de texto via API (se disponível)
- Tente configurar `response_modalities=[\"TEXT\"]` no primeiro turno do Gemini Live, ativando apenas `input_audio_transcription`.
- Receba a transcrição do usuário como texto, decida a rota e, somente então, renegocie (ou continue) a sessão com `response_modalities=[\"AUDIO\"]` para a segunda viagem.
- Isso requer que a API permita mudar `response_modalities` entre turnos ou usar duas sessões distintas.

**Benefício**: elimina totalmente a geração de áudio desnecessária na primeira viagem.

## Decisão
Escolhemos a **Opção A** por ser a mais simples de implementar com base no SDK atual do Google Gemini Live (versão 2.18.1), que já permite receber transcrição de entrada sem gerar áudio de saída na primeira viagem, mediante o uso de `input_audio_transcription` e não enviando `turn_complete` até que a intenção seja conhecida.

A Opção B requer integração e manutenção de um modelo STT local (Vosk), o que aumenta a complexidade e o tamanho do binário. A Opção C depende de um recurso da API que ainda não está disponível (não é possível mudar `response_modalities` por turno na versão atual do SDK).

## Implementação
1. No transporte de voz (`core/gemini_live_voice.py`), modificar o `_receive_loop` para:
   - Quando estiver em modo de escuta (gate aberto) e receber `interim_input_transcription` ou `input_transcription`, atualizar `self._input_text`.
   - Após receber texto suficiente (ou após o fim da fala indicado por server-side VAD), chamar `self._decide_turn_route()` **antes** de processar o `model_turn` (áudio) do turno.
   - Se o turno for classificado como AÇÃO, definir `self._play_generated_audio = False` e `self._turn_direct = False` (já é o padrão, mas garantir que não mudemos acidentalmente).
   - Se for CONVERSA, definir `self._play_generated_audio = True` e `self._turn_direct = True` (já ocorre atualmente).
   - No processamento do `model_turn`, apenas tocar o áudio se `self._play_generated_audio` for True (já está assim no código).
2. Garantir que o turno não seja considerado completo (`turn_complete`) até depois que o executor termine e a segunda viagem seja iniciada (já é assim hoje: o turno só termina após o `speak()` da segunda viagem).
3. Preservar todos os existentes mecanismos de reconexão, barge-in, wake word híbrida e detecção de eco.

## Testes
- Os testes existentes de fluidez de conversa (`test_voice_conversation_fluidity.py`) devem continuar passando.
- Um novo teste de spike (local, sem rede) deve verificar que, em um turno de ação, o áudio do modelo é recebido pelo transporte mas não é tocado (`_play_generated_audio` permanece False) e que o marco `primeira_viagem_descartada` medido pelo cronômetro é próximo de zero (ou, ao menos, muito menor que os 6,7 s atuais). Este teste deve falhar com o comportamento atual e passar após a implementação.

## Impacto Esperado
- Redução da latência mediana em turnos de ação de ~7,8 s para ~1,1 s (apenas a segunda viagem + executor).
- Nenhum impacto em turnos de conversa (já estão < 500 ms percebido).
- Manutenção da regra de verdade da ZARA: o modelo nunca declara sucesso de ação por conta própria.

## Próximos Passos
1. Implementar a alteração no transporte de voz conforme descrito.
2. Executar os testes de unidade existentes para garantir não regressão.
3. Executar o teste de spike para validar a redução da latência.
4. Após confirmação, liberar a mudança somente após nova checagem de cota e designação explícita de modelo forte (conforme bloqueio original da tarefa).

--- 
*Decisão tomada em 23/08/2026, com base nos spike offline do SDK google-genai 2.18.1 e nos dados de latência produzidos em 22/08/2026.*