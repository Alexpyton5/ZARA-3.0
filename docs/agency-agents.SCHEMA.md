# Contrato inicial do catálogo Agency (Lab V1)

O arquivo esperado é `agency-agents.json`. Por padrão, a ZARA procura em
`ZARA3_HOME/data/` quando `ZARA3_HOME` está definido; caso contrário, em
`LOCALAPPDATA/ZARA3/data/`. O campo `agency_roster_path` da política persistida
do Lab pode apontar para outro caminho **absoluto** com o mesmo nome de arquivo.
Não coloque o catálogo no Git enquanto a fonte real não for confirmada.

```json
{
  "schema_version": 1,
  "agents": [
    {
      "id": "pesquisador-01",
      "name": "Pesquisador",
      "capabilities": ["pesquisa"],
      "description": "Pesquisa fontes públicas"
    }
  ]
}
```

`schema_version` pode ser omitido (valor implícito 1). Uma lista diretamente
na raiz também é aceita para compatibilidade. Cada agente precisa de `id` e
`name` não vazios; `id` deve ser único (sem diferenciar maiúsculas/minúsculas).
`capabilities` é uma lista de textos e `description` é texto opcional. O limite
é 1000 agentes e 2 MiB. Formato inválido ou caminho que não termina em
`agency-agents.json` deixa a Agency indisponível; arquivo ausente a deixa
dormente. O Lab permanece utilizável em ambos os casos.

`READY` significa apenas **catálogo lido**. Não cria equipe, não convida
participantes, não concede turno, não escolhe modelo e não chama provedor.
Essas etapas exigem gates separados e teste antes de habilitar execução.
Os 291 TOML em `.codex/agents/` não são este catálogo.
