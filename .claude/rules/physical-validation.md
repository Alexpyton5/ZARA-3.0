# Regras de validação física — ZARA 3.0

## Princípio

A ZARA é voice-first. A aceitação do produto é Alex falar e a máquina obedecer.
Nenhum harness substitui isso.

## Nunca peça 90 comandos

A pirâmide é obrigatória.

### Nível 1 — micro smoke (1 a 3 comandos)

Ligados **diretamente** ao delta que acabou de entrar. Se falhar, para tudo, não sobe para o nível 2.

Trio de recuperação de voz:

1. "Zara, que horas são?"
2. "Zara, diminua o volume."
3. "Zara, abra o YouTube."

### Nível 2 — família pequena

Wake sem clicar, volume, brilho, night light, Chrome, YouTube, barge-in ("Zara, pare").

### Nível 3 — regressão ampla

Só depois de baseline estável comprovada.

## Formato do pedido de teste

Nunca escrever "abra a ZARA". Existem múltiplas linhagens de build no repositório.
Sempre:

```
ALEX_OPEN_THIS_EXE:
<caminho absoluto exato>

BUILD_ID:
BUILD_TIMESTAMP:
SHA256:
SOURCE_REVISION:

TESTE 1: <frase exata a falar>
ESPERADO: <o que deve acontecer fisicamente na tela/no Windows>

TESTE 2: ...
TESTE 3: ...
```

Para cada teste, dizer o que observar **no Windows**, não o que a ZARA deve responder.
Se a única prova disponível for a frase que a ZARA falou, o teste não vale nada.

## Registro do resultado

Para cada comando físico, registrar:

- frase falada (exata)
- o que a ZARA respondeu
- o que aconteceu de fato no Windows
- divergência entre os dois

Divergência entre resposta e realidade é **incidente de falso sucesso** e vira tarefa própria.

## Diferencial texto vs voz

Toda investigação de voz precisa rodar a **mesma frase** por texto e por voz no **mesmo build**.

- texto OK + voz falha → divergência está antes do dispatcher (mic/STT/wake/normalização/IPC)
- texto falha + voz falha → divergência está no intent/executor, e é mais barato depurar por texto
- texto OK + voz "responde bonito mas não age" → suspeitar de caminho que fala resposta de modelo sem executar ação

## Antes de pedir qualquer teste ao Alex

1. o build foi executado diretamente e sobreviveu ao boot
2. o backend empacotado dentro do build corresponde ao source testado
3. o hash foi capturado
4. o build anterior foi preservado
5. nenhuma dependência não relacionada foi mutada

Se qualquer item falhar, não pedir teste. Alex não é o ambiente de CI.
