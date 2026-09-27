# Checklist físico do controle Windows

## Pré-condições

Executar no Windows real, com ZARA aberta, backend iniciado e logs disponíveis. Não usar o ambiente Linux para declarar sucesso físico.

## Testes controlados

1. Solicitar abertura de Bloco de Notas; confirmar janela visível e retorno `verificado=true`.
2. Solicitar foco da janela pelo título exato; confirmar que ela ficou em primeiro plano.
3. Solicitar fechamento; confirmar que a janela desapareceu sem finalização forçada.
4. Repetir abertura com aplicativo não permitido; confirmar rejeição.
5. Solicitar foco de título ambíguo; confirmar rejeição sem clicar na janela errada.
6. Encerrar a ZARA pela bandeja; confirmar que o modo residente mantém o backend somente quando essa política estiver habilitada.
7. Fechar de verdade; confirmar que o sidecar termina e não fica processo órfão.

## Evidências

Guardar data, versão do build, resultado retornado, screenshot opcional e trecho de log sanitizado. Não registrar tokens, caminhos pessoais desnecessários ou conteúdo de janelas privadas.

## Critério

A etapa só passa quando todas as ações permitidas forem confirmadas no Windows e todas as ações proibidas forem rejeitadas. Os testes automatizados em Linux validam apenas contrato, allow-list e comportamento de plataforma não suportada.
