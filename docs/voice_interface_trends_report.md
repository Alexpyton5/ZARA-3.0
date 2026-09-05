# Tendências de Interface de Voz para ZARA

## 1. Componentes Recomendados

   - **HUD Visual**: 
        * Orb: indicador de estado (idle, listening, processing, speaking) com animação suave.
        * Waveform: mostrar o nível de áudio em tempo real durante a captura de microfone e reprodução.
        * Barras de frequência: para representar visualmente o espectro de áudio durante a fala do usuário e da assistente.

   - **Feedback Sonoro (Earcons)**:
        * Sons distintos para: início de escuta, processamento, conclusão de tarefa, erro, barge-in detectado.
        * Usar áudio espacial para dar sensação de direção quando relevante (ex: som vem da direção do microfone).

   - **Multimodal**:
        * Combinar voz com toque (tela) e olhar (gaze tracking) para confirmação de ações críticas.
        * Permitir que o usuário inicie uma consulta por voz e confirme com toque ou olhar.
        * Usar rastreamento de olhar para determinar o foco do usuário e ajustar a resposta (ex: mostrar informações na tela onde o usuário está olhando).

   - **Personalidade Adaptativa**:
        * Ajustar o tom, o ritmo e o nível de detalhes da resposta com base no histórico do usuário, no contexto atual e no estado emocional detectado (por análise de tom de voz e escolha de palavras).
        * Aprender com as interações passadas para personalizar a experiência (ex: preferência por respostas curtas ou detalhadas).

## 2. Tokens Visuais

   - **Cores**:
        * Idle: #6B7280 (cinza neutro)
        * Listening: #3B82F6 (azul claro)
        * Processing: #8B5CF6 (roxo)
        * Speaking: #10B981 (verde)
        * Error: #EF4444 (vermelho)

   - **Tamanhos e Animações**:
        * Orb: diâmetro de 80px em estado idle, expandindo para 100px ao ouvir, com pulsação suave.
        * Waveform: altura de 40px, largura total do contêiner, com barras que variam em altura com base no nível de áudio.
        * Barras de frequência: 5 barras, cada uma com largura de 8px, espaçamento de 4px, altura variando entre 20px e 60px.

   - **Transições**:
        * Todas as mudanças de estado devem ter transições de 200ms para suavidade.

## 3. Padrões de Conversa Natural

   - Baseado na instrução do sistema do Gemini Live (arquivo `core/gemini_live_voice.py`):
        * Responder em português do Brasil quando o usuário falar em português.
        * Respostas naturais, úteis, objetivas e humanas.
        * Nunca afirmar que realizou uma ação no computador; apenas anunciar o resultado verificado pelo sistema.
        * Quando receber texto iniciado por "FALE_EXATAMENTE:", pronuncie somente o texto após os dois-pontos.
        * Nunca inventar números, medidas, horas, etc.; se não souber, dizer que não sabe.
        * Se não entender, pedir para repetir.
        * Se não souber responder a uma pergunta, oferecer o que se pode fazer.
        * Falar como uma pessoa: sem fórmulas prontas, sem repetir a mesma frase, sem enrolação.

   - Tendências adicionais:
        * Usar respostas curtas (uma ou duas frases) a menos que o usuário peça detalhes.
        * Incorporar elementos de empatia e inteligência emocional (ex: detectar frustração e ajustar o tom).
        * Manter o contexto da conversa para lidar com perguntas de follow-up.
        * Oferecer saídas gracejosas de erros e sugerir alternativas.

## 4. Acessibilidade

   - **Para usuários com deficiência auditiva**:
        * Fornecer legendas ou transcrição em tempo real da fala da assistente.
        * Oferecer modo de texto completo como alternativa à voz.

   - **Para usuários com deficiência de fala**:
        * Permitir entrada por texto ou por métodos alternativos (como dispositivos de comutação ou rastreamento ocular).
        * Modo literal para usuários com espectro autista (desativar interpretações idiomáticas e de sarcasmo).

   - **Para usuários com déficit cognitivo**:
        * Detectar sinais de sobrecarga cognitiva (hesitação, repetições) e simplificar a estrutura dos comandos, reduzir o ritmo da fala.
        * Fornecer respostas claras e concisas, evitando jargões.

   - **Para usuários com deficiência visual**:
        * Garantir que todos os elementos visuais do HUD tenham contraste adequado e sejam descritos por leitores de tela (via ARIA labels).
        * Permitir navegação por voz sem depender de elementos visuais.

   - **Geral**:
        * Cumprir WCAG 2.2 para interações baseadas em voz.
        * Oferecer controle de volume independente do sistema.
        * Permitir que o usuário ajuste a velocidade da fala da assistente.

## 5. Fontes

   - Não há menção específica a fontes nos resultados da pesquisa. Porém, para a interface visual (se houver texto na tela), recomenda-se:
        * Use uma fonte sans-serif legível em tamanhos pequenos (ex: Inter, San Francisco, Roboto).
        * Garantir que a fonte seja disponível em vários pesos para hierarquia visual.
        * Considerar fontes que suportem bem o português do Brasil (com acentos e caracteres especiais).

## Observações sobre a Implementação Atual

   - A ZARA já implementa alguns desses conceitos:
        * O gate Vosk local está desligado por padrão, permitindo ouvir continuamente e barge-in real.
        * O wake word é feito por transcrição no `ipc_handlers._on_gemini_live_turn`.
        * Há um filtro de eco por conteúdo para evitar que a assistente ouça a si mesma.
        * O sistema de transporte de áudio pode ser modo "renderer" (usando o AEC do Chromium) ou "local".
        * A instrução do sistema já contém muitos dos princípios de conversa natural e proibição de falso sucesso.

   - Lacunas identificadas (tendências não implementadas):
        * Elementos visuais HUD (orb, waveform, barras de frequência) não estão presentes no código atual (que parece ser apenas de backend).
        * Feedback sonoro (earcons) não é implementado (apenas níveis de áudio são enviados via IPC).
        * Integração com gaze tracking, toque e outros modos de entrada não está presente.
        * Personalidade adaptativa baseada em histórico e emoção não está implementada.
        * Recursos avançados de acessibilidade (como legendas em tempo real, modo literal para autismo) não estão presentes.

## Próximos Passos Sugeridos (para o designer)

   - Criar protótipos dos componentes HUD (orb, waveform, barras de frequência) com os tokens visuais sugeridos.
   - Definir um conjunto de earcons para os diferentes estados.
   - Projetar fluxos de conversa que incorporem multimodalidade (voz + toque + olhar).
   - Desenvolver diretrizes para a personalidade adaptativa com base no contexto do usuário.
   - Garantir que o design seja acessível conforme as diretrizes acima.

 ---

 *Este relatório foi baseado em pesquisas de tendências de interface de voz para 2024-2026 e na análise do código atual da ZARA.*