# Onde ficam as chaves da ZARA

Este arquivo **não contém nenhuma chave**. Ele diz onde elas moram, onde se gera
uma nova, e o que para de funcionar sem cada uma. Pode ser lido por qualquer um
sem risco.

## O único lugar que vale

```
C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\config\api_keys.json
```

É daí que a ZARA lê. Está protegido pelo `.gitignore` (linha `config/api_keys*`),
então **nunca sobe para o GitHub**. Verificado em 16/08/2026: nenhum commit do
histórico contém nenhuma dessas chaves.

Existe também um backup antigo, `config/api_keys.json.antes-do-telegram`. Está
igualmente protegido. Foi mantido de propósito — não apagar sem conferir antes o
que tem dentro.

## Regra

Chave só existe nesses dois arquivos. Se aparecer em qualquer outro lugar —
outro `.txt`, um script, uma pasta de outro programa — é vazamento e tem que ser
apagada de lá.

Foi o que aconteceu em 15/08/2026: o chaveiro inteiro foi colado em
`C:\Users\alexp\omniroute\chave-do-roteador.txt`, incluindo o token do Telegram.
Limpo em 16/08. Naquele arquivo vai **só a chave do roteador**, uma linha, gerada
no painel dele em Endpoints.

## O que é cada chave

| Campo no arquivo | Onde se gera outra | O que para sem ela |
|---|---|---|
| `gemini_api_key` | aistudio.google.com/apikey | **Tudo.** É o único cérebro vivo hoje: dos 13 modelos registrados, só os dois Gemini respondem. Sem ela a ZARA fica muda. |
| `telegram_bot_token` | Telegram → `@BotFather` → `/token` (ou `/revoke` para trocar) | A ponte do celular. Sem ela Alex não fala com a ZARA de fora de casa. Quem tiver esse token lê as mensagens e responde no lugar dele. |
| `groq_api_key` | console.groq.com/keys | A reserva de outro provedor. Hoje ela responde, mas estoura o limite de 8000 tokens por minuto com o prompt cheio. |
| `nvidia_api_key` | build.nvidia.com | Nada — **já está vencida** (401 nos três modelos em 16/08/2026). |
| `hermes_url` / `hermes_api_key` | local, do próprio Hermes | O Supercérebro. É serviço local, risco menor. |
| `zai_api_key` / `xai_api_key` | — | Vazias. Os modelos correspondentes nunca funcionaram. |

Todas são de camada gratuita. O prejuízo de um vazamento não é dinheiro: é a
cota ser queimada por outro e a ZARA parar.

## Como trocar uma chave

1. Gerar a nova no site da tabela acima.
2. Abrir `config/api_keys.json` no Bloco de Notas.
3. Substituir **só o valor** entre aspas, mantendo as vírgulas.
4. Fechar e reabrir a ZARA.

Se o JSON ficar inválido (vírgula a mais ou a menos), a ZARA sobe sem chave
nenhuma. Na dúvida, pedir para o Claude Code fazer a troca.
