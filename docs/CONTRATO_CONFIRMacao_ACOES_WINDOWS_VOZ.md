# Contrato de confirmação para voz e controle Windows

O núcleo de ações já possui um único broker de confirmação. A solicitação retorna um desafio temporário; a aprovação precisa usar o mesmo fingerprint da ação; o desafio é consumido uma única vez e expira em 30 segundos. O cancelamento remove o desafio sem executar a ação.

Ações de risco médio, como abrir, fechar ou focar janelas, exigem `confirm=true` ou política explícita. Ações de alto risco usam o desafio privado e não aceitam o booleano legado.

O fluxo de voz deve ser:

1. Transcrever o comando.
2. Mostrar a ação e o alvo.
3. Pedir confirmação quando a política exigir.
4. Permitir “cancelar” ou expirar automaticamente.
5. Executar via `ActionRegistry`.
6. Verificar a pós-condição.
7. Falar apenas o resultado comprovado.

Nenhuma capacidade deve ser marcada como “controle total” antes do teste físico no Windows. Voz e navegador estão preparados; controle Windows físico, OCR nativo e carregamento correto de página continuam pendentes de validação.
