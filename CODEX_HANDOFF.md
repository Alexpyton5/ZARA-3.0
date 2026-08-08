# Passagem de bastão — ZARA 3.0

Atualizado em: 2026-08-08 14:00 (America/Bahia)
Uso: copie integralmente este arquivo para uma nova tarefa do Codex quando precisar trocar de conta.

## Prompt para o próximo Codex

Você está assumindo a ZARA 3.0 como Mentor técnico principal. Continue de onde a equipe anterior
parou; não reinicie a auditoria do zero e não promova código sem evidência.

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
- Raiz principal estava limpa antes desta documentação.
- 62 testes Python, Ruff e compileall passaram na baseline.
- `npm ci`, `npm ls`, typecheck, lint (0 erros/47 warnings), builds Vite/Electron, PyInstaller e
  electron-builder passaram.
- Confirmação HIGH one-shot/HMAC/TTL, gates de capability e testes IPC foram implementados.
- SSRF foi fechado para fetch/browser/download: schemes, userinfo, localhost, endereços não
  públicos/metadata, DNS, peer e redirects são validados; streaming é limitado.
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

Essa branch ainda **não está promovida**. A revisão encontrou e a equipe está corrigindo:

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

Não faça merge enquanto a branch não estiver limpa, todos os testes não passarem e dois revisores
independentes não derem veredito **APROVADO PARA PROMOÇÃO**.

### Próximas ações exatas

1. Conferir mensagens/estado do agente que corrige `lab/realtime-web-core` e exigir novo commit
   incremental, sem amend/rebase dos commits acima.
2. No worktree, executar:

   ```powershell
   python -m pytest -q
   python -m ruff check main.py core memory integrations tests build_exe.py
   python -m compileall -q main.py core memory integrations tests build_exe.py
   git diff --check main...HEAD
   ```

3. Revisar manualmente o delta e repetir ataques focalizados: gzip bomb, query de 1 milhão de
   caracteres, resolver DNS travado, redirect+304 cross-origin, corrida de cache e payload máximo.
4. Fazer smoke ao vivo inofensivo do DDG e da pesquisa com cache temporário, sem chaves pagas.
5. Só após aprovação, na raiz principal:

   ```powershell
   git merge --no-ff lab/realtime-web-core -m "feat: add bounded realtime web research"
   ```

6. Repetir suíte Python e todos os gates frontend; construir sidecar e pacote Electron.
7. Testar a pesquisa via IPC no **sidecar PyInstaller**, pois o caminho `multiprocessing spawn` no
   executável congelado é um gate obrigatório. Depois fazer smoke do Electron empacotado.
8. Conferir que sidecar dentro do pacote é byte a byte igual ao recém-gerado, gerar novos SHA-256,
   atualizar `README.md`, `OPERATIONS.md`, `MENTOR_TAKEOVER_REPORT.md` e este arquivo.
9. Criar novo commit/tag de certificação somente com todos os gates verdes.

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
