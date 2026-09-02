# Política de isolamento de testes — ZARA 3.0

## Por que existe

Na madrugada de 2026-09-02, testes automatizados mexeram no volume real do
computador do Alex, e sobrescreveram (pela terceira vez na mesma sessão) um
arquivo de estado real (`config/telegram_lido.json`). Ambos os incidentes
tinham a mesma causa: um teste **achava** que estava mockando um ponto de
entrada, mas o código de produção não passava por ali — o monkeypatch não
tinha efeito nenhum, e a chamada real acontecia.

## As três categorias (ver `pyproject.toml` → `[tool.pytest.ini_options]`)

- **SAFE** — lógica pura, sem hardware, sem browser real, sem arquivo real,
  sem SO real. Não precisa de marcação — é o padrão implícito de qualquer
  teste sem `@pytest.mark.live`.
- **SANDBOX** — usa recursos descartáveis (diretório temporário, processo
  fake, SQLite temporário, API mockada). Também roda por padrão.
- **LIVE** — toca volume, brilho, janela, app, browser, microfone, áudio,
  hardware físico ou rede externa real. **Bloqueado por padrão.**

## Estado real hoje (2026-09-02)

Nenhum teste da suíte está formalmente marcado `@pytest.mark.safe` ou
`@pytest.mark.sandbox` ainda — os markers existem e estão registrados, mas
classificar retroativamente ~1600 testes é trabalho de auditoria, não uma
correção de uma madrugada. O que **existe e funciona agora**:

1. Os três markers (`safe`, `sandbox`, `live`) estão registrados em
   `pyproject.toml` e qualquer teste pode usá-los.
2. `tests/conftest.py::pytest_collection_modifyitems` pula automaticamente
   qualquer teste marcado `@pytest.mark.live`, a menos que
   `ALLOW_LIVE_TESTS=1` esteja definido no ambiente.
3. `tests/conftest.py::_bloquear_hardware_real_por_padrao` — rede de
   segurança de nível mais baixo: os seletores conhecidos de escrita de
   hardware (`_set_windows_volume`, `_set_windows_mute`,
   `_set_windows_brightness`) viram fakes por padrão em TODO teste, mesmo
   sem marcação alguma, a menos que `ALLOW_LIVE_TESTS=1`. Um teste que
   precisa validar o comportamento real desses seletores continua livre
   para sobrescrever com seu próprio `monkeypatch` — como isso roda depois
   desta fixture, o teste sempre vence.
4. `tests/conftest.py::pytest_sessionstart`/`sessionfinish` — trava de
   execução única (ver `TEST_RUN_POLICY.md`).
5. `ZARA_TEST_MODE=1` é definido automaticamente para toda sessão de teste.

## O que NÃO está pronto (PARTIAL, não READY)

- **Adapters mockáveis por assunto** (`VolumeAdapter`, `BrightnessAdapter`,
  `WindowAdapter`, `ClipboardAdapter`, `FileSystemAdapter`, `BrowserAdapter`,
  `ProcessAdapter`) — não foram criados. `os_ops.py` já tem seletores
  privados razoavelmente isolados (`_read_windows_volume`,
  `_set_windows_mute`, etc.), mas não é uma camada de Adapter formal com
  Fake correspondente. Introduzir essa camada é um refactor real, cruzando
  várias áreas de ação (arquivos, browser, processos) — trabalho de uma
  tarefa própria e delimitada, não algo para fazer "de passagem" numa
  correção de incidente.
- **Classificação completa dos ~1600 testes** em SAFE/SANDBOX/LIVE — não
  feita. A rede de segurança de hardware cobre os seletores conhecidos de
  áudio; não cobre (ainda) browser real, microfone, TTS real, apps reais,
  clipboard real, terminal destrutivo, sleep/shutdown — esses continuam
  dependendo de cada teste mockar corretamente por conta própria, sem uma
  segunda camada de proteção.

## Regra prática para quem for adicionar um teste novo

Se o teste chama qualquer `@action` que controla o PC:

1. Confira se a função já tem um seletor privado mockável
   (`_read_windows_*`/`_set_windows_*` em `core/actions/os_ops.py` é o
   padrão de referência).
2. Se não tiver, **crie o seletor antes de escrever o teste** — não invente
   um nome de mock e assuma que o código de produção vai chamá-lo.
3. Depois de escrever o teste, rode ele sozinho e observe se algo mudou de
   verdade no PC (volume, brilho, janela). Se mudou, o mock está incompleto.
