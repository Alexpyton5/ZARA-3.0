# Caminho 100% Gratuito de Ponta a Ponta sem Chave do Gemini

Este documento descreve o caminho completo para executar a ZARA 3.0 com zero dependência de chaves de API externas, utilizando apenas componentes locais e gratuitos.

## Visão Geral

O caminho gratuito utiliza:
- **STT (Speech-to-Text)**: faster-whisper (modelo base ou pequeno)
- **LLM (Large Language Model)**: Ollama com qwen3:4b
- **TTS (Text-to-Speech)**: Kokoro ou Piper (voz portuguesa pf_dora)
- **VAD (Voice Activity Detection)**: Silero VAD (opcional)
- **Orquestração**: Pipeline personalizado ou Pipecat (quando disponível)

Todos os componentes rodam localmente, sem custo e sem necessidade de conexão à internet após o download inicial dos modelos.

## Componentes e Instalação

### 1. Dependências Python

Instale as seguintes bibliotecas no ambiente virtual da ZARA:

```bash
.venv\Scripts\pip install faster-whisper kokoro-onnx piper-tts onnxruntime torch sounddevice numpy ollama
```

> Nota: O pacote `ollama` é o cliente Python para interagir com o serviço Ollama local.

### 2. Ollama e Modelo qwen3:4b

- Instale o Ollama de https://ollama.com
- Inicie o serviço: `ollama serve`
- Baixe o modelo: `ollama pull qwen3:4b`

### 3. Modelos de TTS

#### Kokoro (recomendado para português)
O modelo Kokoro e as vozes serão baixados automaticamente na primeira inicialização pelo `LocalVoiceEngine`.
- Modelo: https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/kokoro-v1.0.onnx
- Voz pf_dora: https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files/voices/pf_dora.bin

#### Piper (alternativa)
Se preferir Piper, baixar o modelo português correspondente do Hugging Face rhasspy/piper-voices.

### 4. Modelos de STT

O faster-whisper baixará o modelo especificado (default: "base") na primeira uso.

## Implementação

O caminho gratuito está implementado em:

- `core/local_pipeline.py`: Classe `LocalPipeline` que orquestra o fluxo STT -> LLM (Ollama) -> TTS.
- `voice/local_engine.py`: Engine de voz local que já suporta faster-whisper + Kokoro/Piper + Silero VAD.

O `LocalPipeline` inicializa o `LocalVoiceEngine` com configuração zero-API e conecta-se ao Ollama local para geração de respostas.

## Teste de Funcionalidade

Para testar o caminho gratuito sem qualquer chave de API:

1. Certifique-se de que o Ollama está rodando e o modelo qwen3:4b está disponível.
2. Limpe variáveis de ambiente de chaves de API (GEMINI_API_KEY, DEEPGRAM_API_KEY, etc.) para garantir que nenhum serviço externo seja acionado.
3. Execute o teste:

```bash
.venv\Scripts\python.exe tests\test_local_pipeline.py
```

O teste verifica:
- Inicialização bem-sucedida do pipeline local
- Conexão com o Ollama (pode ser mockado se o serviço não estiver disponível)

## Fluxo de Operação

1. **Escuta**: O microfone capta áudio; o VAD detecta início de fala.
2. **STT**: O áudio é transcrito por faster-whisper para texto em português.
3. **LLM**: O texto é enviado para o Ollama (modelo qwen3:4b) que gera uma resposta.
4. **TTS**: A resposta é convertida em áudio por Kokoro (ou Piper) e reproduzida pelos alto-falantes.
5. **Loop**: O processo repete enquanto o pipeline está ativo.

## Vantagens

- **Zero custo**: Não há taxas de uso de APIs externas.
- **Privacidade total**: Todos os dados permanecem na máquina local.
- **Funciona offline**: Após o download inicial dos modelos, não é necessária conexão à internet.
- **Baixa latência**: Processamento local evita delays de rede.

## Limitações e Requisitos de Sistema

- **RAM**: Recomendado mínimo 8 GB para operação confortável (Ollama qwen3:4b ~2.5 GB, outros componentes consumem memória).
- **CPU**: Um processador moderno é suficiente; GPU não é necessária para os modelos usados.
- **Espelho em disco**: Aproximadamente 3-4 GB para os modelos (Whisper base, Ollama qwen3:4b, Kokoro).

## Próximos Passos

- Integrar o `LocalPipeline` ao sistema de IPC da ZARA para que possa ser selecionado como backend de voz.
- Adicionar opção no frontend para escolher entre pipeline local e pipeline baseado em nuvem (Gemini).
- Melhorar a detecção de voz e barge-in usando o Silero VAD mais avançado.
- Permitir troca fácil entre diferentes modelos locais (ex: tentar outros modelos Ollama como phi3, mistral, etc.).

## Conclusão

Com o caminho descrito acima, a ZARA 3.0 pode operar totalmente independente de chaves de API externas, oferecendo uma experiência de voz privada, gratuil e funcional em qualquer máquina Windows 11 com recursos modestos.

--- 
*Documento gerado como parte da tarefa F5.1 - Caminho 100% gratuito de ponta a ponta sem chave do Gemini.*