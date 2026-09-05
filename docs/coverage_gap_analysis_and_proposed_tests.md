# Análise de Lacunas de Cobertura e Proposta de Testes de Alto Valor

## Resumo da Cobertura (pytest --cov=core)

Executamos os testes leves nos módulos de voz, IPC, Telegram, segurança e inicialização. O relatório de cobertura combinado mostrou:

- **cobertura total**: 19% (15708 statements, 12730 missing)
- **Módulos críticos com baixa cobertura**:
  - `core/gemini_live_voice.py`: 13% coberta, 674 statements missing
  - `core/ipc_handlers.py`: 27% coberta, 1778 statements missing
  - `core/autonomy_policy.py`: 0% coberta, 165 statements missing (inicialização / política de iniciativa)
  - `core/url_security.py`: 77% coberta, 28 statements missing (segurança de URLs)
  - `core/telegram_approval_adapter.py`: 100% coberta (nenhuma lacuna)

## Lacunas de Maior Impacto

### 1. Voz (`gemini_live_voice.py`)
Linhas ausentes incluem tratamento de reconexão, detecção de atividade de voz (VAD), processamento de áudio de entrada/saída, gerenciamento de estado de conexão e callbacks de erro. Muitos blocos de `try/except` e condições de estado não são exercitados pelos testes atuais.

### 2. IPC (`ipc_handlers.py`)
Linhas ausentes cobrem:
- Validação e logs de parâmetros de entrada em handlers de comando
- Tratamento de erros de IPC (timeouts, desconexões)
- Fluxos de confirmação e cancelamento de solicitações
- Integração com o módulo de segurança (SuperCerebro) e gates de risco
- Rotas de fallback e tratamento de mensagens não reconhecidas

### 3. Inicialização / Política de Iniciativa (`autonomy_policy.py`)
Cobertura 0%. Este módulo contém a lógica que decide quando a ZARA pode tomar iniciativas proativas com base em configuração de utilidade, limites de interrupção, períodos silenciosos e histórico de conselhos. Nenhum teste existente exercita as funções de carregamento de configuração, avaliação de utilidade ou aplicação de thresholds.

### 4. Segurança de URL (`url_security.py`)
Embora a cobertura seja razoável (77%), as linhas ausentes tratam de:
- Validação de esquemas de URL perigosos (file://, ftp://, etc.)
- Detecção de endereços IP privados e reservados em diferentes formatos (IPv4, IPv6, localhost)
- Bloqueio de URLs com credenciais embutidas
- Verificação de redirecionamentos que levam a destinos privados

## Três Testes de Maior Valor Propostos

### Teste 1: Simulação de Reconexão e VAD em Voz
- **Objetivo**: Exercitar os caminhos de reconexão automática e detecção de atividade de voz em `gemini_live_voice.py`.
- **O que faria**: Simular queda de conexão de áudio, envio de frames de áudio com e sem fala, e verificar que o módulo tenta reconectar, ajusta o VAD e não trava.
- **Valor**: Cobriria dezenas de linhas ausentes relacionadas a loops de reconexão, callbacks de erro e atualização de estado de conexão.

### Teste 2: Fluxo de Comando IPC com Falha e Confirmação
- **Objetivo**: Testar o tratamento de erros e fluxos de confirmação em `ipc_handlers.py`.
- **O que faria**: Invocar um handler de comando com parâmetros inválidos, simular timeout de IPC, e testar o caminho de confirmação/cancelamento quando o gateway estiver indisponível. Verificar logs e retornos de erro apropriados.
- **Valor**: Cobriria linhas ausentes de validação, tratamento de exceções, gates de segurança e caminhos de fallback.

### Teste 3: Avaliação de Política de Iniciativa
- **Objetivo**: Exercitar a lógica de decisão de iniciativa em `autonomy_policy.py`.
- **O que faria**: Carregar diferentes configurações de utilidade, thresholds e históricos de conselhos; então chamar a função que decide se a iniciativa deve ser permitida e verificar os resultados contra os limites configurados.
- **Valor**: Trazeria a cobertura de 0% para um nível significativo, garantindo que o comportamento proativo da ZARA esteja testado e seguro.

## Próximos Passos
Ao receber esta análise, o próximo worker (provavelmente o designer ou desenvolvedor) pode usar estas propostas para criar testes unitários direcionados, aumentando a cobertura nos pontos críticos sem modificar o código de produção.