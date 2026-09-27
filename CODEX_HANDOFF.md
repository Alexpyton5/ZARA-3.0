# Passagem de bastão — ZARA 3.0

Atualizado em: 2026-08-08 14:10 (America/Bahia)
Uso: copie integralmente este arquivo para uma nova tarefa do Codex quando precisar trocar de conta.

Estado da sessão: **PAUSADA A PEDIDO DO USUÁRIO PARA TROCA DE CONTA**. Todos os agentes auxiliares
foram interrompidos e os dois repositórios estão limpos; nada ficou apenas na memória do agente.

## Prompt para o próximo Codex

Você está assumindo a ZARA 3.0 como Mentor técnico principal. Continue de onde a equipe anterior
parou; não reinicie a auditoria do zero e não promova código sem evidência.

**Prioridade dada diretamente por Alex:** faça a ZARA funcionar de ponta a ponta primeiro. Não deixe
endurecimento avançado de segurança consumir a obra e não desative navegador ou recursos úteis por
riscos teóricos do uso local. Mantenha as proteções básicas contra travamento, perda de dados,
segredos e ações perigosas; registre hardening adicional no backlog e volte a ele depois da
funcionalidade.

### Autoridade e regras do projeto

- A única raiz principal é `C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002`.
- Trabalhe na raiz principal ou em worktrees isolados e revisáveis.
- Todas as outras ZARAs são standby/backup. Não sincronize uma árvore inteira por cima da principal.
- `D:` está marcado como volume sujo. Não grave, construa, instale ou copie nada para/dele até
  `chkdsk` administrativo e nova verificação.
- Custo obrigatório: R$ 0. Não compre serviços e não use API paga sem autorização humana nova.
- Nunca exponha chaves, tokens, arquivos `.env` ou `config/api_keys.json`.
- `RISK != PERMISSION`: ações HIGH exigem desafio/prova explícita, curta e vinculada à ação; não
  aceite um booleano `confirm=true` como autorização HIGH.
- Supercérebro/Hermes deve iniciar OFF. Não ative controle físico em testes.
- Preserve dados e memórias em AppData. Não apague backups nem faça limpeza destrutiva por suposição.

### Baseline já concluída

- Repositório Git principal criado e protegido por `.gitignore`.
- Baseline: commit `3d817a2`.
- Tag recuperável: `zara-3.0-principal-2026-08-08`.
- Documentação viva de passagem: commit `2bcf0b6` na branch `main` (será atualizado por novo commit).
- Raiz principal está limpa e a melhoria experimental não foi misturada nela.
- 62 testes Python, Ruff e compileall passaram na baseline.
- `npm ci`, `npm ls`, typecheck, lint (0 erros/47 warnings), builds Vite/Electron, PyInstaller e
  electron-builder passaram.
- Confirmação HIGH one-shot/HMAC/TTL, gates de capability e testes IPC foram implementados.
- Proteções SSRF básicas entraram em fetch/browser/download: schemes, userinfo, localhost,
  endereços não públicos/metadata, DNS, peer e redirects são validados; o risco residual avançado
  do navegador está documentado abaixo para uma fase posterior.
- Corrida de boot Electron/sidecar foi corrigida com uma promessa compartilhada de readiness.
- Smoke do pacote passou: backend pronto, renderer sem falha, sem boot race, stderr zero e
  Supercérebro OFF/desconectado.
- `verify_pc_voice_binding.py` passou 50/50 sem efeitos físicos.

Pacote certificado da baseline:

- sidecar SHA-256: `639E4D80FA54C2A50F77EF161D1C0C49AF5CD7FF24638401BD44EAEF9B18BBCC`
- app unpacked SHA-256: `67DC2A7036860A68E5312C212C31B8772AC463ED0289FCC44897867F55075E89`
- instalador SHA-256: `4D63B88D050CF4110D93DBC59D47A21C8E4E191DBA2AC881CFFBF8BD832CEA41`

### Trabalho em andamento: pesquisa web em tempo real

Worktree isolado:

`C:\Users\alexp\AppData\Local\ZARA3\lab-workspaces\worktrees\TASK-ZARA-REALTIME-WEB-001`

Branch: `lab/realtime-web-core`

Commits preservados, sem rewrite:

- `ab67d99` — núcleo inicial de pesquisa/cache/citações;
- `be1b62d` — limites, deadline inicial, DDG, truncamento e HTTP 304.
- `88b6f59` — **checkpoint WIP pausado**, contendo toda a terceira rodada de correções e testes.

Essa branch ainda **não está promovida**. O WIP contém:

1. decompression bomb por `httpx.iter_bytes()`;
2. prazo não absoluto por DNS/HTTP síncrono no Windows;
3. query, região, headers, validators e payload IPC sem teto rígido;
4. 304 após redirect podendo revalidar representação de outra URL/origem;
5. corrida em que resposta antiga sobrescreve cache mais novo.

O desenho aprovado que está sendo implementado é:

- `Accept-Encoding: identity`, rejeição fail-closed de qualquer `Content-Encoding` comprimido e
  leitura por `iter_raw()`;
- query/região/headers/validators/URLs/resultados com limites de runtime e schema;
- pesquisa inteira em processo `spawn` supervisionado, no máximo dois processos, Pipe de tamanho
  limitado, deadline interno 40 s e corte duro `terminate`/`kill` antes do IPC Electron de 60 s;
- runtime hook PyInstaller para `multiprocessing.freeze_support()`;
- validators removidos em redirect e 304 aceito somente para a mesma URL canônica em cache;
- UPSERT compare-and-set por `retrieved_at`, impedindo resposta velha de substituir nova;
- `output` compacto e `data` estruturado limitado, sem duplicar o payload integral.

O checkpoint WIP compila e o Ruff passa, mas os testes focados terminaram em **46 PASS / 6 FAIL**.
As falhas são de encaixe da implementação interrompida, não da ZARA principal:

1. o filho do supervisor já envia JSON por bytes, mas o pai ainda tenta ler como objeto pickle
   (`UnpicklingError: invalid load key, '{'`);
2. cinco testes com transporte HTTP simulado não fornecem o endereço do peer que a nova validação
   passou a exigir, então falham com `Connected peer address is unavailable` antes das asserções.

Correção direta esperada: ler o Pipe com `recv_bytes(maxlength=...)`, decodificar JSON limitado e
adaptar os mocks para expor um peer público/pinado (ou permitir ausência apenas no transporte de
teste). Depois rodar novamente os gates. Não faça merge com esses seis testes falhando.

Há uma dívida de segurança conhecida no navegador Playwright: prevalidar DNS e validar o peer após
a resposta não elimina completamente uma janela de DNS rebinding. Alex decidiu que isso fica no
backlog de hardening; **não desative o navegador por causa disso agora**. A prioridade é provar o
fluxo funcional local.

### Próximas ações exatas

1. Abrir o worktree no commit `88b6f59`; ele está limpo e contém todo o WIP.
2. Corrigir primeiro as seis falhas descritas acima, sem ampliar novamente a auditoria de segurança.
3. No worktree, executar:

   ```powershell
   python -m pytest -q
   python -m ruff check main.py core memory integrations tests build_exe.py
   python -m compileall -q main.py core memory integrations tests build_exe.py
   git diff --check main...HEAD
   ```

4. Fazer smoke ao vivo inofensivo do DDG e da pesquisa com cache temporário, sem chaves pagas.
   Antes da terceira rodada, o DDG real já retornou três resultados em aproximadamente três segundos;
   repita porque o transporte mudou depois desse smoke.
5. Garanta que o `output` da action contenha fontes/citações úteis para Hermes. Hoje a integração
   Hermes entrega somente `result.output`; um texto que diga apenas “Collected N sources” não basta
   para a ZARA usar a pesquisa, mesmo que `result.data` esteja correto.
6. Com testes e smoke funcionais verdes, fazer uma revisão curta de regressão e então, na principal:

   ```powershell
   git merge --no-ff lab/realtime-web-core -m "feat: add bounded realtime web research"
   ```

7. Repetir suíte Python e todos os gates frontend; construir sidecar e pacote Electron.
8. Testar a pesquisa via IPC no **sidecar PyInstaller**, pois o caminho `multiprocessing spawn` no
   executável congelado é um gate obrigatório. Depois fazer smoke do Electron empacotado.
9. Conferir que sidecar dentro do pacote é byte a byte igual ao recém-gerado, gerar novos SHA-256,
   atualizar `README.md`, `OPERATIONS.md`, `MENTOR_TAKEOVER_REPORT.md` e este arquivo.
10. Depois da pesquisa web, priorizar funcionamento real: chat com um provedor gratuito/local,
    memória/lembretes via IPC e voz em hardware real. Só então retomar hardening avançado.
11. Criar novo commit/tag de certificação somente com todos os gates verdes.

### Panorama simples para Alex

**Funciona e foi comprovado:**

- a ZARA principal abre como aplicativo empacotado;
- a tela carrega sem tela preta;
- o backend inicia e conversa com a tela;
- a corrida de inicialização foi corrigida;
- o instalador e o executável foram gerados;
- a lógica de 50 comandos de voz para controle do PC passou 50/50 sem executar efeitos reais;
- a ZARA inicia com Supercérebro desligado, como deve;
- a baseline tem testes, build e smoke verdes e pode ser recuperada pela tag Git.

**Existe, mas ainda precisa de prova real:**

- conversar com um modelo usando as chaves/provedores locais;
- microfone, fala, áudio e interrupção ouvidos por uma pessoa;
- memória, lembretes e sala de equipe usados de ponta a ponta pela interface;
- conexão real com Hermes/Supercérebro;
- navegador em uso prolongado e os diferentes sites da internet.

**Está quebrado/incompleto, mas isolado:**

- a nova action de pesquisa web em tempo real está no laboratório, com seis testes de integração
  falhando no checkpoint WIP; ela não está no aplicativo principal nem no instalador certificado;
- o volume D e os backups que estavam sendo copiados nele estão presos/sujos; isso não afeta a
  raiz principal em C.

Resumo honesto: a fundação e o aplicativo principal estão estáveis, mas a ZARA ainda não foi
certificada como assistente completa no uso diário. O próximo Mentor deve parar de expandir a
auditoria e provar os fluxos reais um a um.

### Pendências que continuam humanas

- ouvir e validar microfone, TTS, interrupção e dispositivos reais;
- chamadas reais aos provedores com chaves locais, sem revelar valores;
- ativação conectada do Hermes/Supercérebro;
- assinatura do instalador para distribuição.

### Estado operacional adicional

- O disco C tinha aproximadamente 7,75 GiB livres; evite builds duplicados e cópias integrais.
- Cinco `robocopy` órfãos D→D (PIDs observados: 1860, 5496, 10812, 11708, 12688) receberam ordem
  de encerramento, mas continuaram presos em I/O. Não tente reparar ou apagar D automaticamente;
  isso provavelmente exige reinicialização e `chkdsk` administrativo.
- Não há motivo para copiar código de D: a raiz C já é a versão principal mais íntegra.

Comece lendo `README.md`, `OPERATIONS.md`, `MENTOR_TAKEOVER_REPORT.md` e o estado Git das duas
árvores. Preserve tudo o que já passou; avance a partir do último checkpoint comprovado.
