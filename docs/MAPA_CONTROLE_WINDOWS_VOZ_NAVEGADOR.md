# Mapa de controle da ZARA

## O que já existe

A ZARA tem captura de voz com cancelamento de eco no renderer, envio de áudio para o backend, abertura segura de URLs HTTP/HTTPS no navegador padrão, pesquisa por URL, perfis reais do Chrome e ações Windows com allow-list e verificação pós-ação.

## O que ainda falta para controle amplo

O controle do computador precisa ser dividido em capacidades: leitura de janelas, OCR, mouse, teclado, arquivos, navegador, mídia, agenda e permissões. Cada capacidade deve ter um adaptador Windows, uma política de risco, confirmação quando necessário, cancelamento, timeout e verificação da consequência.

“Controle total” não deve ser um único botão. É uma coleção de permissões independentes, revogáveis e visíveis no Lab.

## Limites atuais

A abertura de URL prova apenas que a URL foi enviada ao navegador; ainda não prova que a página correta carregou. Voz está funcional como captura/reprodução, mas o fluxo completo de comando por voz depende do provedor/modelo e do teste no Windows. OCR foi preparado em modo simulado e somente leitura; o provedor nativo ainda precisa ser conectado e validado fisicamente.

## Ordem segura

1. Ler e mostrar estado.
2. Simular a ação sem alterar o computador.
3. Pedir confirmação conforme o risco.
4. Executar somente via ActionRegistry.
5. Verificar a pós-condição.
6. Registrar no Obsidian o comando, o resultado e a evidência sanitizada.
7. Permitir cancelar ou revogar a capacidade.
