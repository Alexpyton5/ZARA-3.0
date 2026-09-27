# Teste do ciclo Autopilot e modo residente

## Ciclo completo validado

O teste de aceitação percorre a sequência `pesquisa → evidência → chat do pesquisador → candidato DRAFT → teste aprovado → aprovação CEO → ativação → nova versão → rollback → registro no Obsidian`.

O teste usa um fetcher controlado e não acessa fontes externas. Isso torna o resultado repetível e evita que uma mudança na internet altere a validação do produto.

## Comunicação no Obsidian

Cada participante grava uma mensagem JSON em uma nota Markdown dentro de `Zara-Memoria/Chat-Lab/`. Os campos obrigatórios são `mission_id`, `role`, `state` e `summary`. Evidências são referenciadas por hash, e mensagens com aparência de segredo são rejeitadas antes da gravação.

Papéis aceitos: `RESEARCHER`, `ARCHITECT`, `ENGINEER`, `CODER`, `TESTER`, `REVIEWER`, `CEO` e `ZARA`.

Estados aceitos: `OBSERVED`, `ANALYZING`, `PLANNED`, `IMPLEMENTING`, `TESTING`, `REVIEWING`, `WAITING_CEO`, `APPROVED`, `REJECTED` e `ROLLED_BACK`.

## Modo residente do Windows

A ZARA já inicia o sidecar Python ao abrir o Electron, cria a bandeja do Windows e mantém a janela oculta quando o usuário clica no X. Assim, o Lab e o scheduler continuam trabalhando mesmo sem a interface aberta.

O encerramento real continua disponível no menu da bandeja em **Sair da ZARA**. Nesse caminho, o Electron fecha o stdin do sidecar, aguarda a saída limpa e força somente a árvore de processos pertencente à ZARA se necessário.

O modo residente não instala serviço oculto, não executa código descoberto automaticamente e não promove Skills sem aprovação explícita. O computador precisa estar ligado e a ZARA precisa permanecer em execução na bandeja.

## Limitação importante

Fechar a bandeja ou escolher “Sair da ZARA” interrompe o trabalho. Para funcionar com o Windows desligado ou com o processo encerrado, seria necessário um serviço externo ou hospedagem permanente, o que é uma decisão de implantação separada.
