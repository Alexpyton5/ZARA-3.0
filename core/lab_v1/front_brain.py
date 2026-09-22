"""One owner-selected conversational brain, using the existing Lab store and runs.

This is a conversation policy, not a mission planner. It never delegates or
retries a failing call twice; when the chosen brain cannot answer, a single
authorized fallback transport answers once. The existing V1 authority protects
turns across processes.
"""
from dataclasses import replace
from core.lab_v1.domain import MessageKind, RoleName, SessionState, new_id, now

DEFAULT_BRAIN = 'gpt-5.6-luna'
BRAINS = {DEFAULT_BRAIN: 'Luna', 'gpt-6-astra': 'Astra',
          'gpt-5.6-sol': 'Sol', 'gpt-5.6-terra': 'Terra'}
# Free OpenCode brains (user's local OpenCode login). Exposed from the actual
# local catalog only -- the dropdown never fabricates models.
OPENCODE_PROVIDER = 'opencode'
OPENCODE_BRAIN_LIMIT = 8
_SESSION = 'session_zara_front_v1'
_TEAM = 'team_zara_front_v1'
_KEY = 'front_brain_v1'
_SYSTEM = (
    'Voce e ZARA, a mesma assistente pessoal do Alex independentemente do modelo '
    'e do canal. Responda em portugues, de forma curta e natural. '
    'O bloco ZARA_RUNTIME_CONTEXT descreve factualmente o aplicativo, canal e '
    'capacidades deste turno; nao invente nem contradiga esse estado. '
    'Texto, voz e Telegram sao canais da mesma ZARA, nunca um ambiente separado. '
    'Acoes locais passam pelo dispatcher antes deste turno conversacional: nao '
    'afirme que executou uma acao sem o recibo do backend. Nao exponha raciocinio interno.'
)


def _failure(code, error):
    return {'success': False, 'code': code, 'error': error,
            'response_origin': 'front_brain_policy'}


def _provenance(run, brain, *, success):
    """Run receipt shaped for the UI. Reported identity stays factual: identity is
    compared against the *executed* run routing, never against the owner-facing
    brain choice -- a fallback reply must reach the UI, not reject itself."""
    reported = run.model_reported
    mismatch = bool(reported and reported != run.model)
    status = 'MISMATCH_REJECTED' if mismatch else ('MATCHED' if reported else 'UNREPORTED')
    return {
        'success': success,
        'response_origin': 'front_brain_run',
        'engine': brain,
        'run_id': run.id,
        'model_requested': run.model,
        'model_reported': reported,
        'provider': run.provider_id,
        'provenance_status': status,
        'rerouted': mismatch,
    }


class FrontBrain:
    def __init__(self, runtime):
        self.runtime, self.store = runtime, runtime.store

    def _opencode_models(self):
        """Cerebros OpenCode para o seletor, a partir do catalogo local real.

        O descritor nao traz custo, entao a unica sinalizacao factual de
        gratuidade e o proprio nome do modelo (sufixo '-free'); o restante e
        espalhado entre familias para nao virar uma parede de um unico modelo.
        A disponibilidade real continua vindo do probe do registry.
        """
        adapter = self.runtime.registry.get(OPENCODE_PROVIDER)
        if adapter is None:
            return ()
        ids = tuple(dict.fromkeys(item.model_id for item in adapter.declared_models))
        free = [i for i in ids if i.endswith('-free')]
        direct = [i for i in ids if i.endswith('glm-5.3-flash')]
        gpt = [i for i in ids if i.endswith('-codex') or i.endswith('-codex-max')]
        rest = [i for i in ids if i not in set(free) | set(direct) | set(gpt)
                and not i.removeprefix('opencode/').startswith('claude-opus')
                and 'nvidia' not in i]
        ordered = list(dict.fromkeys(free + direct + gpt + rest))
        return ordered[:OPENCODE_BRAIN_LIMIT]

    def _provider_for(self, model):
        return OPENCODE_PROVIDER if isinstance(model, str) and model.startswith('opencode/') else 'codex_cli'

    def _current(self):
        with self.store._connect() as conn:
            row = conn.execute('SELECT value FROM schema_meta WHERE key=?', (_KEY,)).fetchone()
        # Legacy auto/API preferences cannot authorize premium front usage.
        if row and row[0] in BRAINS:
            return row[0]
        if row and row[0] in self._opencode_models():
            return row[0]
        return DEFAULT_BRAIN

    def _model_status(self, model):
        """Allow the first real turn after official account/catalog discovery.

        ``model_status`` deliberately calls a discovered model unproven until
        an inference receipt exists.  That is useful evidence vocabulary, but
        it cannot be a precondition for the very first inference or the front
        brain deadlocks forever.  The adapter still rechecks the plan account
        inside every invocation and persists the factual result.
        """
        provider = self._provider_for(model)
        status = self.runtime.registry.model_status(provider, model)['availability']
        if status != 'DISCOVERED_UNPROVEN':
            return status
        adapter = self.runtime.registry.get(provider)
        if adapter is None:
            return status
        info = adapter.probe()
        discovered = {item.model_id for item in adapter.declared_models}
        return 'AVAILABLE' if info.availability.can_work and model in discovered else status

    def snapshot(self):
        engines = [
            {'id': model, 'name': name, 'provider': 'codex_cli',
             'status': self._model_status(model)}
            for model, name in BRAINS.items()]
        for model in self._opencode_models():
            engines.append({'id': model, 'name': model.removeprefix('opencode/'),
                            'provider': OPENCODE_PROVIDER,
                            'status': self._model_status(model)})
        return {'success': True, 'current': self._current(), 'engines': engines,
            'health': [], 'session_id': _SESSION,
            # 9Router is deliberately a fallback transport, never a second
            # owner-selected conversational brain.
            'nine_router_fallback': self.runtime.registry.model_status(
                'nine_router', 'alex'
            )['availability'] if self.runtime.registry.get('nine_router') else 'UNKNOWN'}

    def select(self, model):
        if model not in BRAINS and model not in self._opencode_models():
            return _failure('FRONT_MODEL_NOT_ALLOWED',
                            'Escolha Luna, Astra, Sol, Terra ou um cérebro do OpenCode.')
        if self._model_status(model) != 'AVAILABLE':
            return _failure('FRONT_MODEL_UNAVAILABLE', 'Este modelo esta indisponivel. A selecao foi mantida.')
        with self.store._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            busy = conn.execute('SELECT token FROM session_authorities WHERE session_id=?', (_SESSION,)).fetchone()
            if busy and busy[0]:
                return _failure('FRONT_BUSY', 'Aguarde a resposta atual antes de trocar o modelo.')
            conn.execute('INSERT INTO schema_meta(key,value) VALUES(?,?) '
                         'ON CONFLICT(key) DO UPDATE SET value=excluded.value', (_KEY, model))
        return {'success': True, 'engine': model, 'session_id': _SESSION}

    def _session(self):
        # Idempotent INSERTs, not save_session UPSERT: another process may be mid-turn.
        with self.store._connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('INSERT OR IGNORE INTO teams(id,name,objective,created_at,archived) VALUES(?,?,?,?,0)',
                         (_TEAM, 'ZARA Conversa', 'Conversa persistente com Alex', now()))
            conn.execute('INSERT OR IGNORE INTO sessions'
                         '(id,team_id,objective,state,acceptance_criteria,max_delegations,max_cost_usd,revision,created_at,updated_at) '
                         'VALUES(?,?,?,?,?,0,NULL,0,?,?)',
                         (_SESSION, _TEAM, 'Conversa com Alex', 'QUEUED', '[]', now(), now()))
        return self.store.get_session(_SESSION)

    def reply(self, text, *, requested_model=None, history=None, context='',
              result_is_current=None):
        if not isinstance(text, str) or not text.strip() or len(text) > 12000:
            return _failure('FRONT_TEXT_INVALID', 'A mensagem deve ter entre 1 e 12000 caracteres.')
        session = self._session()
        token = new_id('frontturn')
        if self.store.claim_v1(session.id, token):
            return _failure('FRONT_BUSY', 'Existe um turno em andamento ou interrompido; nenhuma chamada foi repetida.')
        try:
            model = self._current()
            if requested_model is not None and requested_model != model:
                return _failure('FRONT_SELECTION_CHANGED', 'O modelo selecionado mudou. Confira o seletor e envie novamente.')
            status = self._model_status(model)
            chosen_provider = self._provider_for(model)
            agent = None
            fallback_used = None
            if status == 'AVAILABLE':
                agent = next((a for a in self.store.list_agents() if a.provider_id == chosen_provider
                              and a.model == model and not a.archived and 'model.text' in a.capabilities), None)
                if agent is None and chosen_provider == OPENCODE_PROVIDER:
                    # Owner picked a fresh OpenCode brain; the run only needs an
                    # in-memory participant -- nothing is persisted without approval.
                    from core.lab_v1.domain import AgentProfile, Lifecycle
                    agent = AgentProfile(
                        id='front-oc-transient', name='OpenCode', provider_id=OPENCODE_PROVIDER,
                        model=model, role=RoleName.MEMBER, lifecycle=Lifecycle.PERMANENT,
                        capabilities=['model.text'],
                    )
            if agent is None:
                # Fallback chain when the chosen brain cannot execute. Never ask Alex.
                # 1) Free OpenCode models (owner login) — preferred over 9Router,
                #    whose account is not configured on this PC.
                for fid in self._opencode_models():
                    s = self.runtime.registry.model_status(OPENCODE_PROVIDER, fid)['availability']
                    if s != 'AVAILABLE':
                        continue
                    agent = next((a for a in self.store.list_agents()
                                  if a.provider_id == OPENCODE_PROVIDER and a.model == fid
                                  and not a.archived and 'model.text' in a.capabilities), None)
                    if agent is None:
                        from core.lab_v1.domain import AgentProfile, Lifecycle
                        agent = AgentProfile(
                            id='front-oc-transient', name='OpenCode', provider_id=OPENCODE_PROVIDER,
                            model=fid, role=RoleName.MEMBER, lifecycle=Lifecycle.PERMANENT,
                            capabilities=['model.text'],
                        )
                    if agent is not None:
                        if agent.model != fid or agent.provider_id != OPENCODE_PROVIDER:
                            agent = replace(agent, provider_id=OPENCODE_PROVIDER, model=fid)
                        fallback_used = (OPENCODE_PROVIDER, fid)
                        break
            if agent is None:
                # 2) 9Router fallback transport (unchanged).
                for fid, fname in [('oc/muse-spark-1.2-contributor-free','nine_router'),('alex','nine_router'),('oc/muse-spark-1.3-contributor-free','nine_router')]:
                    s = self.runtime.registry.model_status(fname, fid)['availability']
                    if s == 'AVAILABLE':
                        agent = next((a for a in self.store.list_agents() if a.provider_id == fname and a.model == fid and not a.archived and 'model.text' in a.capabilities), None)
                        if agent is None:
                            agent = next((a for a in self.store.list_agents() if a.provider_id == 'nine_router' and not a.archived and 'model.text' in a.capabilities), None)
                        if agent is not None:
                            from dataclasses import replace as _fb_replace
                            if agent.model != fid or agent.provider_id != fname:
                                agent = _fb_replace(agent, provider_id=fname, model=fid)
                            fallback_used = (fname, fid)
                            break
                if agent is None:
                    if status != 'AVAILABLE':
                        return _failure('FRONT_MODEL_UNAVAILABLE', 'O modelo selecionado esta indisponivel e o fallback OpenCode/9Router tambem esta offline; tente novamente em instantes.')
                    return _failure('FRONT_PROFILE_UNAVAILABLE', 'O modelo ainda nao tem um perfil comprovado no Lab.')
            agent = replace(agent, max_turns=1)
            # Recent context, bounded at the SQL read and at prompt composition.
            with self.store._connect() as conn:
                rows = conn.execute('SELECT author,content FROM messages WHERE session_id=? '
                                    'ORDER BY created_at DESC,rowid DESC LIMIT 20', (session.id,)).fetchall()
            # Preserve the Lab session across model changes and supplement it
            # with Home-only turns (for example local actions).  Home may be
            # empty in voice/runtime paths, so it must never replace the
            # persistent conversational history.
            merged = [{'author': row['author'], 'content': row['content']} for row in rows]
            if history:
                home = [{'author': 'Alex' if m.get('role') == 'user' else 'ZARA',
                         'content': str(m.get('content', ''))}
                        for m in history[-20:] if m.get('role') in ('user', 'assistant')][::-1]
                seen = {(row['author'], row['content']) for row in merged}
                merged.extend(row for row in home
                              if (row['author'], row['content']) not in seen)
            rows = [row for row in merged
                    if not (row['author'] == 'Alex' and row['content'] == text.strip())][:20]
            recent, remaining = [], 16000
            for row in rows:
                entry = f'{row["author"]}: {row["content"]}'[-4000:]
                if len(entry) > remaining:
                    break
                recent.append(entry)
                remaining -= len(entry)
            prompt = str(context or '')[:10000] + '\nContexto recente:\n' + '\n'.join(reversed(recent)) + '\n\nAlex: ' + text.strip()
            session.state = SessionState.RUNNING
            session.updated_at = now()
            self.store.save_session(session)
            _tried = {model}
            run, result = self.runtime._run_agent(session, agent, prompt, _SYSTEM, timeout_s=120)
            # Um unico passe de reposicao, limitado ao catalogo: se a chamada
            # falhar por cota/fundos (dados da conta) ou o provedor responder
            # vazio/expirar (confiabilidade variavel dos modelos gratuitos),
            # reponho uma vez para o proximo cerebro OpenCode disponivel; o
            # resultado de cada tentativa fica registrado. Sem loop infinito,
            # sem pergunta ao Alex.
            _REPOSITION_MARKS = ('funds', 'quota', 'cota', 'credit', 'crédito',
                                 'rate limit', 'nao retornou resultado',
                                 'expirou', 'sem mensagem')
            # Estados de conta/confiabilidade que autorizam reposicao pela
            # availability classificada: o codex chega com codigos compactos
            # (CODEX_USAGELIMITEXCEEDED -> QUOTA_EXHAUSTED) que nao casam nos
            # marcadores de texto. Mismatch (outro modelo) e decisao do dono
            # (DISABLED_BY_OWNER_POLICY) NAO reposicionam.
            _REPOSITION_STATES = ('QUOTA_EXHAUSTED', 'RATE_LIMITED', 'AUTH_REQUIRED',
                                  'BUSY', 'OFFLINE', 'PROVIDER_ERROR', 'ERROR')

            def _reposition_allowed(_result):
                if isinstance(_result.error, str) and any(
                        mark in _result.error.lower() for mark in _REPOSITION_MARKS):
                    return True
                return getattr(_result, 'availability', None) in _REPOSITION_STATES

            while (not result.ok and _reposition_allowed(result)):
                _candidates = [fid for fid in self._opencode_models()
                               if fid not in _tried
                               and self.runtime.registry.model_status(OPENCODE_PROVIDER, fid)['availability'] == 'AVAILABLE']
                if not _candidates:
                    break
                fid = _candidates[0]
                _tried.add(fid)
                agent = replace(agent, provider_id=OPENCODE_PROVIDER, model=fid)
                fallback_used = (OPENCODE_PROVIDER, fid)
                run, result = self.runtime._run_agent(session, agent, prompt, _SYSTEM, timeout_s=120)
            if result_is_current is not None:
                try:
                    current = bool(result_is_current())
                except Exception:
                    current = False
                if not current:
                    # Preserve the Run as factual provider evidence without
                    # promoting an interrupted answer into canonical history.
                    session.state = SessionState.QUEUED
                    session.updated_at = now()
                    self.store.save_session(session)
                    return {
                        **_failure('FRONT_TURN_STALE', 'O turno foi interrompido.'),
                        **_provenance(run, model, success=False),
                        'session_id': session.id,
                        'fallback': fallback_used,
                    }
            # Bind both canonical messages to the factual Run. A voice caller
            # can then purge the complete interrupted turn without deleting
            # the Run receipt itself.
            self.runtime._add_message(
                session, kind=MessageKind.USER, author='Alex', content=text.strip(), run_id=run.id,
            )
            session.state = SessionState.COMPLETED if result.ok and str(result.text or '').strip() else SessionState.BLOCKED
            session.updated_at = now()
            self.store.save_session(session)
            if session.state == SessionState.BLOCKED:
                mismatch = result.error == 'CODEX_MODEL_MISMATCH' or bool(
                    run.model_reported and run.model_reported != run.model)
                code = 'CODEX_MODEL_MISMATCH' if mismatch else 'FRONT_PROVIDER_FAILED'
                error = ('O provedor retornou outro modelo; a resposta foi rejeitada.' if mismatch else
                         'Nao consegui responder com o modelo selecionado; nao usei outro.')
                return {**_failure(code, error), **_provenance(run, model, success=False),
                        'session_id': session.id, 'fallback': fallback_used}
            self.runtime._add_message(session, kind=MessageKind.AGENT, author='ZARA', content=result.text,
                                      author_agent_id=agent.id, run_id=run.id)
            return {**_provenance(run, model, success=True), 'response': result.text,
                    'session_id': session.id, 'fallback': fallback_used}
        finally:
            self.store.release_v1(session.id, token)
