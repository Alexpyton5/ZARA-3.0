# Agency Agents no ZARA Lab

Fonte: [msitarzewski/agency-agents](https://github.com/msitarzewski/agency-agents),
commit `053ddbbf392a1688fc7043d81529f47ef2cf86c8` (consultado em 2026-09-24).
Licença MIT, copyright (c) 2025 AgentLand Contributors. O aviso completo está em
[`LICENSE.txt`](LICENSE.txt) e também dentro do módulo Python empacotado.

O catálogo inclui **264 perfis** em **18 divisões**, definidos pelo `divisions.json`
da fonte. A contagem de 267 arquivos Markdown nas pastas de topo inclui três
documentos em `strategy/` sem frontmatter de agente. Eles são playbooks, não
perfis, e a própria fonte exclui `strategy/` da lista de divisões.

`catalog_payload.py` contém todos os perfis completos, comprimidos em um módulo
Python. A importação estática em `core.lab_v1.agency_catalog` faz o PyInstaller
incluí-los no executável sem depender de diretórios externos ou caminhos de
desenvolvimento. Cada perfil tem ID estável `divisão/nome-do-arquivo`, nome,
descrição, origem e SHA-256 do arquivo original.

API para o Lab:

```python
from core.lab_v1.agency_catalog import (
    catalog_info,
    get_template,
    list_templates,
    select_template,
)

list_templates()                              # metadados, sem instruções extensas
list_templates(query="backend", limit=10)
get_template("engineering/engineering-backend-architect")
select_template("projetar uma API segura", role="Backend Architect")
catalog_info()                                # contagem, divisões, fonte, licença
```

`get_template` e `select_template` devolvem o campo `instructions` com o Markdown
integral. O conteúdo é material de terceiros para orientar um trabalhador já
autorizado. Ele não concede acesso a ferramentas, não substitui as regras do
Lab e não autoriza ações no computador.

Para atualizar a fonte em outro commit, execute:

```text
python -m core.lab_v1.agency_data.generate_catalog --source CAMINHO_DO_CLONE
```

Depois atualize este registro de origem e confira a contagem da nova versão.
