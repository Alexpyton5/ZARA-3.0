# PESQUISA PROATIVIDADE: Como a ZARA Antecipa Sem Incomodar

> **Entregável da tarefa t_f6332ebd** — Pesquisador UX
> **Data:** 23/08/2026 | **Versão:** 1.0

---

## Resumo Executivo

A ZARA já possui **infraestrutura de base** para proatividade graduada (autonomia, diário automático, percepção de ambiente, aprovação remota, engine de iniciativa). O que falta é **política de decisão unificada** que cruze esses sinais e decida *quando* e *como* agir — observando, sugerindo, preparando, pedindo aprovação ou executando — com **métricas de utilidade**, **limites anti-incômodo**, **rollback** e **custo R$0 / privacidade local**.

---

## 1. Componentes Recomendados (Arquitetura de Proatividade)

| Camada | Componente Atual | Gap | Recomendação |
|--------|------------------|-----|--------------|
| **Percepção** | `core/perception/ambiente.py` (ociosidade, janela ativa, bateria, CPU, rede, clima) | Não expõe "frontier de workflow" (pós-commit, pós-merge, idle qualificado) | Adicionar detector de *boundary events* (fim de tarefa, mudança de app, silêncio prolongado) |
| **Memória/Contexto** | `core/diario_auto.py` + `core/sugestoes_momento.py` | Sugestões só olham *passado* (agregação diária), não *oportunidade imediata* | Camada `ProactiveSignal` que combina: diario (padrões) + ambiente (agora) + autonomia (nível permitido) |
| **Decisão de Autonomia** | `core/autonomy_policy.py` (4 vereditos) + `core/autonomy_levels.py` (4 níveis) | Dois sistemas paralelos; policy não sabe "utilidade da intervenção" | Unificar em `ProactivityPolicy.decide(signal)` → `ProactivityVerdict` com 5 níveis (ver §2) |
| **Iniciativa** | `core/initiative/engine.py` (Level 2: Scheduled) | Placeholder: utility=0.5 fixo, advice estático, não aprende com feedback | Evoluir para Level 3 (Situation-Aware): utility dinâmico, interruption cost, learning lift |
| **Aprovação** | `core/remote_approval_bridge.py` (single-use, token) | Não tem fila com prioridade, expiração visível, auditoria de *por que* pediu | `ApprovalQueue` com prioridade, TTL visível, motivo da decisão, rollback one-click |
| **Execução/Verificação** | `core/action_registry.py` + `core/ipc_handlers.py` | Sem *post-condition verification* obrigatório no caminho proativo | `ProactiveExecutor` que: prepara → pede aprovação (se nível≥3) → executa → **verifica pós-condição** → reporta só sucesso real |
| **Rollback** | Inexistente | Ação proativa que falha não tem "desfazer" automático | `RollbackRegistry` por action_id: snapshot pré-ação + função inversa (onde reversível) |

---

## 2. Níveis de Proatividade (Plano de 5 Níveis)

Inspirado na taxonomia de **Bui & Evangelopoulos (2026)** — Reactive → Scheduled → Situation-Aware — e na prática da ZARA (autonomy_policy + autonomy_levels + initiative_engine), proponho:

| Nível | Nome | Quando Atua | O Que Faz | Exemplo Real do Dia do Alex | Limite Anti-Incômodo |
|-------|------|-------------|-----------|----------------------------|----------------------|
| **L0** | **OBSERVAR** | Sempre (background) | Coleta sinais: ambiente, diario, padrões, erro repetido. **Não fala.** | Detecta: "Alex abre VS Code → 3 min depois roda `pytest` → 80% das vezes" | Zero: silêncio total |
| **L1** | **SUGERIR** | Alex ocioso ≥ 30s + fora silêncio noturno + limite diário não estourado | Mostra *toast/voice hint* não-intrusivo: "Quer que eu rode os testes?" | Após commit: "Detectei padrão: você roda teste depois de commit. Rodar agora?" | Máx 5/dia; agrupa por chave (comando\|ação); não repete mesma sugestão em 24h |
| **L2** | **PREPARAR** | Sugestão L1 aceita (Alex disse "sim" ou gesto) + ação **reversível** + risco LOW/MEDIUM | Monta *action plan* (args validados, dry-run), mostra preview, **espera confirmação explícita** | "Vou rodar `pytest -q` no repo ZARA. Confirmar?" (mostra comando exato) | Precisa confirmação; dry-run visível; cancela com "não" ou timeout 30s |
| **L3** | **PEDIR APROVAÇÃO** | Ação **irreversível** OU capability HIGH/REMOTE_PC_CONTROL/CODE_EXECUTION/SYSTEM_POWER OU Supercérebro OFF | Envia para **aprovação remota (Telegram/celular)** com contexto completo; **não executa** até Alex aprovar | "Apagar pasta `build/` (2.3 GB). Irreversível. Aprova no celular?" | Fila com prioridade; expira em 10 min; Alex vê *por que* (risco, irreversível, histórico) |
| **L4** | **EXECUTAR** | Ação **reversível** + risco LOW + capability READ_ONLY/LOCAL_PC_CONTROL + confiança ≥ 0.95 + Alex configurou "faz sozinha" + fora silêncio noturno | Executa **sem aviso prévio**, **verifica pós-condição real**, reporta "feito: volume 40%" | "Volume 40%" (ação `os_volume` configurada como AUTO pelo Alex) | Rollback automático se verificação falha; loga no diario_auto com success=false |

> **Regra de Ouro (Fechada):** *Incerteza sempre sobe o nível, nunca desce.* Se falta dado (ambiente degradado, confiança baixa, ação desconhecida) → sobe para L3 no mínimo.

---

## 3. Exemplos Reais do Dia do Alex

| Cenário | Sinais Detectados | Nível Escolhido | Ação da ZARA |
|---------|-------------------|-----------------|--------------|
| **Manhã: abre VS Code no repo ZARA** | Janela=VS Code, processo=Code.exe, ociosidade=0, hora=09:15, diario mostra padrão "abre VS Code → roda pytest em 5 min" | L1 (SUGERIR) | Após 3 min ocioso: *"Costuma rodar os testes agora. Quer que eu rode?"* |
| **Commit pushado** | Git hook detecta push, ambiente mostra terminal ativo, padrão "push → abre PR" | L1 (SUGERIR) | *"Detectei push. Abrir PR no GitHub?"* (ação `browser_new_tab` + URL) |
| **Bateria 15% + não na tomada** | Bateria.percentual=15, na_tomada=False, período=tarde | L2 (PREPARAR) | *"Bateria baixa. Vou ativar economia de energia (brilho 30%, light off). Confirmar?"* |
| **Alex diz "apaga a pasta temp"** | Ação `files_delete` irreversível, capability=FILES_MUTATE, risk=HIGH | L3 (PEDIR APROVAÇÃO) | Envia Telegram: *"Apagar C:\Temp (4.7 GB, 12k arquivos). Irreversível. [SIM] [NÃO]"* |
| **Alex diz "aumenta o volume"** | Ação `os_volume` configurada AUTO (Alex override), risk=LOW, capability=LOCAL_PC_CONTROL, confiança=0.98 | L4 (EXECUTAR) | Executa, verifica `audio_status` → "Volume 65%" |
| **Meia-noite: Alex parado há 2h** | Período=madrugada, ociosidade=7200s, silêncio noturno ativo | **NENHUM** (bloqueado) | Silêncio total. Nada falado, nada mostrado. |

---

## 4. Limites Anti-Incômodo (Hard Guards)

| Guard | Implementação | Parâmetro | Valor Padrão | Configurável |
|-------|---------------|-----------|--------------|--------------|
| **Silêncio Noturno** | `ambiente.periodo in {"noite","madrugada"}` | `silent_start=23`, `silent_end=8` | 23h–08h | Sim (config.yaml) |
| **Limite Diário** | `sugestoes_momento.limite_diario` | `max_suggestions_per_day` | 5 | Sim |
| **Taxa de Interrupção** | `initiative_engine.max_interruptions_per_hour` | `max_per_hour` | 1 | Sim |
| **Anti-Repetição** | `sugestoes_momento.shown_ids` + `initiative_engine._advice_history` | `history_size` | 100 (24h) | Sim |
| **Ociosidade Mínima** | `ambiente.ocioso_segundos >= limite_ociosidade` | `idle_threshold_sec` | 30s | Sim |
| **Confiança Mínima** | `autonomy_policy.CONFIDENCE_FLOOR_*` | `refuse<0.15`, `confirm<0.45`, `notify<0.75` | Conforme policy | Sim (por ação) |
| **Ação Irreversível** | `autonomy_policy._hard_floors: irreversible → PEDE_CONFIRMACAO` | Hard-coded | Sempre ≥ L3 | Não (regra dura) |
| **Supercérebro OFF** | Capability remota → EXIGE_ALEX | Hard-coded | Sempre L3/L4 | Não (regra dura) |
| **Rejeição Prévia** | `remote_approval_bridge.status == "rejected"` → RECUSA | Hard-coded | Não repete | Não (regra dura) |

---

## 5. Métrica de Utilidade (Utility Score)

Função `utility(signal) → [0.0, 1.0]` usada no **L1/L2/L3** para decidir *se* intervir:

```
utility = w1 * pattern_strength
        + w2 * time_savings_estimate
        + w3 * reversibility_bonus
        + w4 * confidence
        - w5 * interruption_cost
        - w6 * recent_rejection_penalty
```

| Fator | Fonte | Peso (w) | Cálculo |
|-------|-------|----------|---------|
| `pattern_strength` | `diario_auto.agregar_por_chave()` → taxa_sucesso × log(ocorrências) | 0.30 | 0.0–1.0 |
| `time_savings_estimate` | Heurística por ação (ex.: `os_volume`=5s, `pytest`=45s, `files_delete`=120s) | 0.20 | Normalizado 0–1 |
| `reversibility_bonus` | `action_spec.reversible` (bool) | 0.15 | 1.0 se reversível, 0.0 se irreversível |
| `confidence` | STT + intent confidence (já vem no request) | 0.15 | 0.0–1.0 direto |
| `interruption_cost` | `ambiente.ocioso_segundos` (quanto mais ocioso, menor custo) + `periodo` (madrugada=∞) | 0.15 | Inverso: ocioso>10min=0.1, ocioso<1min=0.9 |
| `recent_rejection_penalty` | `diario_auto` reações negativas ("não", "errado") nas últimas 24h | 0.05 | 0.0–0.5 |

**Threshold para falar:** `utility ≥ 0.7` (configurável, default do `InitiativeConfig.utility_threshold`).

---

## 6. Rollback & Segurança

| Cenário | Mecanismo | Implementação |
|---------|-----------|---------------|
| **Ação L4 falha verificação pós-condição** | Rollback automático | `RollbackRegistry` registra `pre_state` (snapshot) + `inverse_fn` (ex.: `volume_old` → `os_volume(pre_state)`). Se `verificacao` falha → executa inversa → loga `success=false` no diario |
| **Ação L3 aprovada mas falha execução** | Não há rollback (ação não rodou) | Aprovação marcada `consumed=false` (pode re-tentar); erro logado |
| **Sugestão L1/L2 incorreta (Alex ignora/rejeita)** | Aprendizado negativo | `diario_auto.registrar(reacao_alex="não/ignorado")` → `gerar_sugestoes` detecta `reacoes_negativas ≥ 2` → cria sugestão `revisar_dialogo` |
| **Falso positivo de padrão** | Decaimento temporal | Padrões do diario expiram: `ocorrências` peso decai 10%/dia sem reforço; `utility` cai naturalmente |

---

## 7. Métricas de Acompanhamento (Dashboard)

| Métrica | Fonte | Target | Alerta Se |
|---------|-------|--------|-----------|
| **Intervenções/dia** | `initiative_engine._interruption_times` | ≤ 5 | > 10 |
| **Taxa de aceite L1/L2** | `diario_auto.sugestoes` status `aceita` / total mostradas | ≥ 40% | < 20% |
| **Taxa de sucesso L4** | `diario_auto.entradas` success=true / total L4 | ≥ 95% | < 90% |
| **Falsos positivos (rejeição Alex)** | `diario_auto.reacao_alex` contém "não/errado" | ≤ 10% das intervenções | > 20% |
| **Latência decisão→fala** | `initiative_engine._check_and_act` timestamp | < 200ms | > 500ms |
| **Rollback rate** | `RollbackRegistry` acionados / L4 executadas | ≤ 2% | > 5% |

---

## 8. Implementação Faseada (R$0, Local, Sem Nova Dependência)

| Fase | Entregável | Arquivos Envolvidos | Critério de Pronto |
|------|------------|---------------------|-------------------|
| **F1** (1 semana) | `ProactivityPolicy` unificada (merge autonomy_policy + autonomy_levels + initiative) | Novo: `core/proactivity_policy.py`; adapta: `autonomy_policy.py`, `autonomy_levels.py`, `initiative/engine.py` | Testes: 5 níveis decidem corretamente para 20 ações reais; `utility()` puro, sem I/O |
| **F2** (3 dias) | `ProactiveSignal` agrupa: ambiente + diario + autonomia | Novo: `core/proactivity_signal.py`; usa: `ambiente.py`, `diario_auto.py`, `sugestoes_momento.py` | `obter_sinal_agora()` retorna struct completa em < 50ms |
| **F3** (1 semana) | `ProactiveExecutor` com dry-run, verificação pós-condição, rollback | Novo: `core/proactive_executor.py`; usa: `action_registry`, `remote_approval_bridge` | Executa L2/L3/L4 reais; rollback testado em `os_volume`, `os_brightness` |
| **F4** (3 dias) | Integração no `ipc_handlers.py`: hook pós-comando + loop iniciativa | Edita: `ipc_handlers.py` (ponto único) | ZARA sugere após commit real; aprovação remota funciona end-to-end |
| **F5** (contínuo) | Calibração de pesos `utility` + thresholds por uso real do Alex | Config: `config/autonomy.yaml` (novo) | Métricas §7 no verde por 2 semanas |

---

## 9. Fontes

| # | Fonte | Tipo | Relevância |
|---|-------|------|------------|
| 1 | Bui & Evangelopoulos, *Agentic Coding Needs Proactivity, Not Just Autonomy* (arXiv:2605.06717, 2026) | Paper acadêmico | Taxonomia 3 níveis (Reactive/Scheduled/Situation-Aware), critérios O1–O5, métricas IDQ/CGS/LL |
| 2 | Vaughan, *Proactivity, Not Just Autonomy* (Codex Knowledge Base, 2026-07-14) | Artigo técnico | Mapeia taxonomia para Codex CLI; dados de campo: 52% engagement em boundaries vs 62% dismiss mid-task |
| 3 | Gartner (citado em múltiplas fontes 2026) | Analista | Escada de 4 níveis: Observe → Advise → Act with Approval → Act Autonomously |
| 4 | Zylos Research, *Proactive AI Agents: From Reactive Assistants to Autonomous Monitors* (2026-05-28) | Research blog | Níveis 1–4 com infra requerida; "circuit breakers to prevent runaway behavior" |
| 5 | AIMI Insights, *Agentic AI Maturity Models* (2026) | Framework | Nível 4: approval workflows, rollback plans, audit trails; Nível 5: governance, monitoring |
| 6 | Atolmachev, *Why I am writing acceptance criteria four times for the same agent* (2026) | Blog técnico | Critérios de aceitação mudam por nível: Observe (log), Advise (presentation), Act with Approval (queue, expiry, audit) |
| 7 | Fautons, *The five levels of AI autonomy* (2026) | Blog | L3 = sweet spot atual; "cost of wrong action > cost of checkpoint" |
| 8 | **Código ZARA atual** (core/autonomy_policy.py, autonomy_levels.py, diario_auto.py, sugestoes_momento.py, initiative/engine.py, remote_approval_bridge.py, perception/ambiente.py) | Código-fonte | Base real: 4 vereditos, 4 níveis, diario com sugestões revisáveis, engine Level 2, ambiente sensores, aprovação remota |

---

## 10. Decisões de Design (Registradas para Próximos Bots)

1. **Não criar novo banco** — usa `diario_auto.db` + `sugestoes_momento_state.json` + `zara_autonomy.db` (já existem).
2. **Não instalar dependência** — `psutil`, `sqlite3`, `threading`, `asyncio` já estão.
3. **Policy pura** — `ProactivityPolicy.decide()` não faz I/O, não executa, só decide. Testável 100% unitário.
4. **Um escritor por área** — `proactivity_policy.py` (pesquisador_ux define assinatura), `proactive_executor.py` (designer_ui_ux/implementador), `ipc_handlers.py` (integração, dono do ipc).
5. **Rollback só onde reversível nativamente** — `os_volume`, `os_brightness`, `window_*`, `media_*`. `files_delete`, `os_power`, `terminal` → **nunca L4**, sempre L3.
6. **Alex configura por ação** — `autonomy_preferences` no config.yaml (já suportado em `autonomy_levels.load_user_preferences_from_config`).

---

## Próximo Passo Executável

> **Para @designer_ui_ux / implementador:**
> Criar `core/proactivity_policy.py` com a assinatura:
> ```python
> def decide_proactivity(signal: ProactiveSignal) -> ProactivityVerdict:
>     # retorna: level (0-4), action_name, reason, utility, rollback_possible, requires_approval
> ```
> Usar **apenas** tipos de dados existentes (`AutonomyRequest`, `EnvironmentSignal`, `ActionRiskProfile`, `ApprovalSignal`) — sem nova dependência.

---

**FIM DO RELATÓRIO**