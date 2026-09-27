# Checkpoint — integração Lab, memória e Windows

Data: 2026-09-18

## Implementado neste checkpoint

1. O pacote oficial `core.actions` agora importa `windows_control_foundation`, registrando as ações `windows_app_open`, `windows_app_close`, `windows_window_focus` e `windows_state` no `ActionRegistry` quando o backend inicia.
2. O snapshot IPC de `LabV1Service` agora inclui `central_memory`, com status verificável do Obsidian/cérebro compartilhado, quantidade de notas e indicação de degradação. O vault continua sendo a fonte canônica; o índice SQLite continua derivado.
3. A sala visual do Lab mostra “Memória conectada”, “Memória degradada” ou “Memória não verificada” usando o mesmo snapshot persistido do backend.

## Validação

A compilação sintática dos quatro módulos Python alterados foi concluída com `PYTHON_OK`.

A checagem TypeScript não foi executada neste ambiente porque o wrapper `node_modules/.bin/tsc` não tem permissão de execução no volume Windows montado e o pacote `typescript` não está disponível no caminho direto desse ambiente. Isso não é uma falha declarada do código; precisa ser verificado no Windows pelo build normal.

## Limite honesto

Este checkpoint não declara que o produto inteiro já é um Autopilot 24/7 completo. O scheduler e o runtime do Lab já existem e são iniciados pelo backend, mas pesquisa autônoma ampla, engenharia reversa de repositórios/vídeos, geração segura de skills, revisão multiagente e promoção automática ainda dependem dos fluxos específicos já presentes no projeto e de validação no instalador Windows.

## Próximo passo recomendado

Executar o build no Windows, abrir o Lab e confirmar no cabeçalho o estado da memória central. Depois testar uma ação Windows permitida, como abrir o Bloco de Notas, observando a confirmação pós-ação.

