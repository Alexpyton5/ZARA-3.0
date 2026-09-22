# Tendências de Interface de Voz (2024-2026)

## 1. Componentes recomendados

- **HUD visual**: Orb, waveform, barras de frequência ou visualização AR em Head-Up Display para feedback rico e contextual.
- **Feedback sonoro**: Earcons (tons abstratos) para eventos do sistema, auditory icons (sons naturais) para ações reconhecíveis, e espacialização de voz para sensação de co-presência.
- **Multimodal**: Combinação de voz + toque (tela) + olhar (gaze tracking) para reduzir carga cognitiva e ambiguidade.
- **Personalidade adaptativa**: Persona consistente que ajusta tom, verbosidade e conteúdo conforme contexto, histórico do usuário e estado emocional detectado.

## 2. Tokens visuais

- **Cores e formas**: Use paleta de alta acessibilidade (contraste ≥ 4.5:1). Orb pulsante indica escuta; waveform animado mostra processamento; barras de frequência respondem ao tom da voz.
- **Estado do sistema**: 
  - *Idle*: Orb estático, cor neutra.
  - *Listening*: Orb pulsante em cor primária (ex. azul).
  - *Processing*: Waveform em movimento, cor secundária (ex. roxo).
  - *Speaking*: Orb com ripple sincronizado à fala, cor de sucesso (ex. verde).
  - *Error*: Orb piscante cor de alerta (ex. vermelho) com toast texto curto.
- **Transições suaves**: Animações de fade-in/fade-out ≤ 150ms para evitar sensação de travamento.
- **Adaptação ambiental**: Brilho e opacidade ajustados automaticamente com base em luz ambiente (sensor ou horário).

## 3. Padrões de conversa natural

- **Princípios de design** (baseados nas máximas de Grice adaptadas para voz):
  - *Qualidade*: Responder apenas com informações verificadas; evitar números, medidas ou afirmações não comprovadas.
  - *Quantidade*: Fornecer a menor quantidade de informação necessária para atender ao pedido; respostas de uma ou duas frases.
  - *Relevância*: Manter o foco no intent detectado; evitar informaçõesirrelevantes ou monólogos.
  - *Clareza*: Usar linguagem simples, direta, sem jargões ou expressões idiomáticas que possam não ser compreendidas.
- **Turn-taking**:
  - Sinal claro de fim de fala do usuário (VAD do servidor com `vad_silencio_ms` entre 150-400ms).
  - Pausa curta (< 300ms) antes da ZARA iniciar resposta, indicando processamento.
  - Permitir barge-in: microfone aberto durante a fala da ZARA para detecção de interrupção genuína.
- **Reparo de erro**:
  - Quando não entender, pedir repetição específica (“Não entendi ‘[trecho]’. Pode repetir?”).
  - Nunca afirmar compreensão sem conseguir dizer o que entendeu.
  - Oferecer alternativa açãoável quando não souber responder (“Não sei, mas posso ajudar com …”).
- **Persona e brevity**:
  - Voz consistente (Kore) com tom natural, humano e objetivo.
  - Respostas curtas (máx. 2 frases) salvo solicitação explícita de detalhe.
  - Evitar listas longas; oferecer visualização na tela quando houver múltiplas opções.
- **Contextualização**:
  - Rastrear pronomes e referências ao longo da sessão (“o vermelho”, “amanhã”).
  - Usar histórico de comandos para disambiguação (“ligar a luz do quarto” após falar do quarto).

## 4. Acessibilidade

- **Feedback multimodal**: Sempre acompanhar feedback sonoro com visual (HUD) e/ou haptico (vibração leve) para usuários com deficiência auditiva ou visual.
- **Controle de volume**: Permitir ajuste independente do volume da voz da ZARA e dos earcons via comando de voz ou acessibilidade do sistema.
- **Legibilidade**: Texto suplementar em tela deve seguir WCAG 2.1 AA (fonte mínima 16px, contraste adequado).
- **Comandos alternativos**: Oferecer atalhos de texto ou gesto para funções críticas quando voz não for viável (ambiente ruído, silêncio necessário).
- **Detecção de eco e autoplay**: Utilizar cancelamento de eco do Chromium (modo renderer) e filtro de conteúdo (`_looks_like_own_echo`) para evitar falsos positivos de barge-in.
- **Personalidade neutra**: Evitar estereótipos de gênero, idade ou cultura na persona; permitir escolha de voz e idioma nas configurações.

## 5. Fontes

1. Resourcifi – “Voice User Interface Design: Principles & LLM” (Mar 2026). Disponível em: https://resourcifi.com/insights/voice-ui-design
2. Cheng et al. – “Auditorily Embodied Conversational Agents: Effects of Spatialization and Situated Audio Cues on Presence and Social Perception” (2025). DOI: 10.1145/3772318.3791794
3. Binus University – “UI/UX Designer in 2026: Designing Not Just Screens, But Sound and Gesture Experiences” (Abr 2026). Disponível em: https://binus.ac.id/bandung/dkv/2026/04/15/ui-ux-designer-in-2026-designing-not-just-screens-but-sound-and-gesture-experiences
4. Fuselab Creative – “Voice UI Design Guide 2026 | VUI Best Practices & Examples” (2026). Disponível em: https://fuselabcreative.com/voice-user-interface-design-guide-2026/
5. MDPI – “Evaluating Rich Visual Feedback on Head-Up Displays for In-Vehicle Voice Assistants: A User Study” (2024). DOI: 10.3390/electronics911114

---
*Este documento resume tendências identificadas em pesquisa de mercado e acadêmica até agosto de 2026. As recomendações devem ser validadas com testes de usabilidade específicos ao contexto da ZARA antes de implementação.*