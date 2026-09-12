"""One owner-selected conversational brain, using the existing Lab store and runs.

This is a conversation policy, not a mission planner. It never delegates,
retries, or falls back. The existing V1 authority protects turns across processes.
"""
from dataclasses import replace
from core.lab_v1.domain import MessageKind, SessionState, new_id, now

DEFAULT_BRAIN = 'gpt-5.6-luna'
BRAINS = {DEFAULT_BRAIN: 'Luna', 'gpt-6-astra': 'Astra',
          'gpt-5.6-sol': 'Sol', 'gpt-5.6-terra': 'Terra'}
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


def _provenance(run, model, *, success):
    reported = run.model_reported
    mismatch = bool(reported and reported != model)
    status = 'MISMATCH_REJECTED' if mismatch else ('MATCHED' if reported else 'UNREPORTED')
    return {
        'success': success,
        'response_origin': 'front_brain_run',
        'engine': model,
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

    def _current(self):
        with self.store._connect() as conn:
            row = conn.execute('SELECT value FROM schema_meta WHERE key=?', (_KEY,)).fetchone()
        # Legacy auto/API preferences cannot authorize premium front usage.
        return row[0] if row and row[0] in BRAINS else DEFAULT_BRAIN

    def snapshot(self):
        return {'success': True, 'current': self._current(), 'engines': [
            {'id': model, 'name': name, 'provider': 'codex_cli',
             'status': self.runtime.registry.model_status('codex_cli', model)['availability']}
            for model, name in BRAINS.items()], 'health': [], 'session_id': _SESSION}

    def select(self, model):
        if model not in BRAINS:
            return _failure('FRONT_MODEL_NOT_ALLOWED', 'Escolha Luna, Astra, Sol ou Terra.')
        if self.runtime.registry.model_status('codex_cli', model)['availability'] != 'AVAILABLE':
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
            status = self.runtime.registry.model_status('codex_cli', model)['availability']
            if status != 'AVAILABLE':
                return _failure('FRONT_MODEL_UNAVAILABLE', 'O modelo selecionado esta indisponivel; nao troquei para outro.')
            # Reuse proven profiles; never bootstrap fictional model availability.
            agent = next((a for a in self.store.list_agents() if a.provider_id == 'codex_cli'
                          and a.model == model and not a.archived and 'model.text' in a.capabilities), None)
            if agent is None:
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
                        'session_id': session.id}
            self.runtime._add_message(session, kind=MessageKind.AGENT, author='ZARA', content=result.text,
                                      author_agent_id=agent.id, run_id=run.id)
            return {**_provenance(run, model, success=True), 'response': result.text,
                    'session_id': session.id}
        finally:
            self.store.release_v1(session.id, token)
