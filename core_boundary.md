# Fronteira entre CORE imutável e DADOS persistentes na ZARA 3.0

## CORE (IMUTÁVEL)
- Código fonte da aplicação (diretório `core/`, exceto quando explícitamente marcado como configurável)
- Executáveis gerados (build/, dist/, sidecar builds)
- Scripts de instalação e build (scripts/, build_exe.py, etc.)
- Arquivos de configuração fixa que não contêm dados do usuário (ex.: pyproject.toml, requirements.txt, .gitignore)
- Diretórios de versionamento (.git/, .github/)
- Diretórios de cache e build temporários (.venv/, __pycache__/, .pytest_cache/, .ruff_cache/, .mypy_cache/, .opencode/)
- Recursos estáticos (assets/, frontend/src/ quando parte do bundle)
- Qualquer coisa que, se alterada, afetaria o funcionamento da aplicação e não deveria ser modificada pelo aprendizado ou automação da ZARA.

## DADOS (PERSISTENTES)
Estes são os componentes que sobrevivem a reinstalação, atualização ou limpeza do CORE e devem ser preservados em backups/snapshots:
- `memory/` – memória de longo prazo (long_term.json) e episódica (zara_episodes.sqlite3)
- `config/api_keys.json` – chaves de API (mas será exportado com valores redigidos para segurança)
- `data/` – dados de operação (dev-team-config.json, zara_soul.json, pending_approvals/, etc.)
- `lembretes/` – lembretes do usuário
- `skills/` – skills personalizadas do agente
- `integrations/` – configurações de integração (ex.: hermes/)
- Frontend user data? (frontend/ não contém dados persistentes, apenas código)
- Qualquer arquivo criado pelo usuário ou pela ZARA em LOCALAPPDATA via user_data_dir() que não seja parte do CORE.
- `identity/` – diretório de identidade/persona (core/identity)
- `initiative/` – diretório de automações e iniciativas (core/initiative)
- `perception/` – diretório de percepção (core/perception)
- `lab_coordinator.py`, `autonomy_lab_bridge.py`, `capability_registry.py` – componentes do Task Registry/LAB

## Princípio
O CORE nunca deve ser alterado para "ensinar" a Zara. Todo aprendizado, habilidade, tarefa, lembretes e configuração devem ficar na camada de DADOS.
Um snapshot do cérebro operacional deve exportar apenas a camada de DADOS, com remoção ou redação de segredos (tokens, chaves de API, senhas, etc.).