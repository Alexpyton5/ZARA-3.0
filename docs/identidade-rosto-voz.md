# Identificação por rosto/voz — FRENTE G

Diretriz do Alex: **esposa autorizada (a zoe fala normal); estranho: dizer "você é um estranho" e ignorar.**

## G1 — Desenho do sistema

```
qualquer interação (voz, chat, remoto)
        │
        ▼
IdentityGate.gate_interaction(evidencia)      ← core/identidade_rosto_voz.py
        │
        ├── autorizado (dono/esposa)  → segue o fluxo normal
        ├── estranho                   → fala "você é um estranho" (1x) + IGNORA
        │                                (latch de sessão: próximas falas ignoradas
        │                                 em silêncio até pessoa cadastrada aparecer)
        ├── nao_cadastrado             → cadastro ainda não feito → passa como hoje
        └── sem_evidencia              → passa (ou estranho, com modo_estrito=True)
```

**Fusão rosto+voz:** cada pessoa cadastrada recebe a MAIOR pontuação entre as
modalidades com evidência disponível. Limiares (similaridade de cosseno 0–1):
rosto ≥ 0.60, voz ≥ 0.55. Faixa ambígua [limiar−0.15, limiar) = **estranho**
(fail-closed dentro do subsistema de identidade).

**O que é guardado:** `data/identidade/referencias.json` (pasta de dados do
usuário). Cada referência = hash SHA-256 do embedding + metadados
(modelo, versão, dimensão, qualidade, nº de amostras, data). **Imagem e áudio
crus jamais tocam o disco. O store nasce VAZIO — nenhuma biometria inventada.**

**Threat model:** o portão responde "quem está falando comigo?". Atacante:
pessoa desconhecida falando com o assistente. Fora de escopo nesta versão:
replay de voz gravada (mitigação futura: frase-desafio aleatória + liveness
da câmera). Não é cofre de banco, é proteção doméstica.

**Decisão documentada (modo `nao_cadastrado`):** enquanto o Alex não cadastrar
as referências, o portão passa tudo (comportamento de hoje) com aviso em log.
Travar o app antes do cadastro quebraria o uso dele. Assim que houver qualquer
cadastro, a trava passa a valer de verdade.

**Auditoria:** todo evento vai para `core/audit_log.py`:
`identidade.ok`, `identidade.estranho`, `identidade.cadastro`,
`identidade.nao_reconhecido`, `identidade.sem_evidencia`, `identidade.falha_provedor`.

**LGPD:** `IdentityStore.remover(papel, modalidade?)` apaga a referência.

## Ponto de integração (para a frente A / pipeline de voz)

O portão deve ser chamado no **ponto único de entrada** da interação de voz,
logo após o STT passar pelo portão de wake — `core/ipc_handlers.py`, no
método que processa o resultado do STT (ponto `STT_RESULT result=PASS`):

```python
from core.identidade_rosto_voz import IdentityGate
_portao = IdentityGate()  # criado uma vez no boot do handler

# após STT_RESULT PASS, antes de anexar a mensagem do usuário:
dec = _portao.gate_interaction({"voz": pcm_da_fala, "rosto": frame_ou_None})
if dec.ignorar:
    if dec.fala:  # "você é um estranho" — falar 1x via TTS
        await self._falar(dec.fala)
    return  # ignora: não anexa, não executa
# pessoa autorizada em dec.pessoa ("dono"/"esposa") — segue normal
```

Regras da integração: o portão **nunca** quebra o fluxo de voz (falha interna =
passa com log); a evidência de voz é o PCM do turno; a de rosto é o frame da
webcam quando disponível (opcional).

## G2 — Comportamento (contrato)

| Quem | O que acontece |
|---|---|
| Alex (dono) reconhecido | fluxo normal, nada muda |
| Esposa reconhecida | **a zoe fala normal com ela**, fluxo normal |
| Desconhecido | diz **"você é um estranho"** (frase exata, 1 vez) e **ignora** tudo depois |
| Pontuação ambígua | tratado como estranho (fail-closed) |
| Sem cadastro ainda | passa como hoje (ver decisão acima) |

Constante de contrato: `FRASE_ESTRANHO = "você é um estranho"` em
`core/identidade_rosto_voz.py`. Não alterar sem decisão do Alex.

## G3 — Cadastro das referências (depende do Alex)

Script: `scripts/cadastrar_identidade.py`

```
python scripts/cadastrar_identidade.py --papel dono   --modalidade voz
python scripts/cadastrar_identidade.py --papel dono   --modalidade rosto
python scripts/cadastrar_identidade.py --papel esposa --modalidade voz
python scripts/cadastrar_identidade.py --papel esposa --modalidade rosto
```

O que o Alex (e a esposa) precisam fazer, quando ele quiser:

1. **Voz:** num lugar silencioso, dizer 3 frases em tom normal
   ("ZARA, sou eu." / "ZARA, pode me ouvir?" / "ZARA, sou eu, pode falar.").
2. **Rosto:** na frente da câmera do PC, olhar direto, rosto bem iluminado;
   3 capturas (frente, leve esquerda, leve direita), 3 s cada.
3. O script valida qualidade mínima e nº de amostras e grava a referência.

Com `--simulacao` o fluxo completa de ponta a ponta para teste, sem biometria
real. Sem a flag, o script mostra os passos reais e avisa honestamente que a
captura real ainda não está plugada.

## Provedores reais (trabalho futuro, fora desta frente)

- **Rosto:** modelo ONNX de embedding facial (ex.: ArcFace) rodando local;
  `pontuar` = similaridade de cosseno entre embeddings.
- **Voz:** modelo de embedding de locutor (ex.: ECAPA-TDNN) sobre o PCM do
  turno; `pontuar` = similaridade de cosseno.
- Ambos implementam o protocolo `ProvedorBiometrico` (`cadastrar`/`pontuar`)
  e são injetados no `IdentityGate`. Até lá, `ProvedorNaoImplementado`
  levanta erro explicativo em vez de fingir medição (frente C).
