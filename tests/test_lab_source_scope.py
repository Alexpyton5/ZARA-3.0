"""select_source_scope: natural-language -> real module mapping.

Context (2026-09-12): the owner typed "QUERO QUE VOCE MELHORE O TEMPO DE
RESPOSTA DA VOZ DA ZARA ELA AINDA DEMORA MUITO DE ME RESPONDER" into the ZARA
Lab and the mission died immediately with SOURCE_SCOPE_NOT_IDENTIFIED,
because select_source_scope only ever recognized a file path written
literally in the objective text. The owner is not a programmer and does not
know module names, so this made the Lab's core promise ("describe WHAT you
want, ZARA decides HOW") false for its main use case.

These are read-only filesystem checks against the real repository tree (no
Lab session, no sqlite, no ZARA3_HOME involved), so no isolation fixture is
needed beyond the autouse ones already in conftest.py.
"""
from __future__ import annotations

from pathlib import Path

from core.lab_v1.source_scope import SCOPE_NOT_IDENTIFIED_MESSAGE, select_source_scope

WORKSPACE = Path(__file__).resolve().parents[1]


def test_explicit_path_still_wins_over_inference():
    """Non-regression: a literal path in the objective is the strongest
    signal of intent and must keep beating any inferred guess."""
    result = select_source_scope(
        WORKSPACE, 'Conserte core/model_router.py: a rota AUTO esta escolhendo modelo errado.')
    assert result == ['core/model_router.py']


def test_the_real_owner_complaint_resolves_to_real_voice_or_latency_modules():
    """The exact real-world failure: no path was typed, only a symptom."""
    objective = ('QUERO QUE VOCE MELHORE O TEMPO DE RESPOSTA DA VOZ DA ZARA '
                 'ELA AINDA DEMORA MUITO DE ME RESPONDER')
    result = select_source_scope(WORKSPACE, objective)

    assert result, 'a queixa real do dono nao pode voltar vazia'
    for relative in result:
        assert (WORKSPACE / relative).is_file(), f'{relative} nao existe de verdade no disco'

    # Real, hand-verified voice/latency-relevant modules in this repository.
    # core/cronometro.py is literally "ZARA-LATENCIA-MEDIDA-001 - onde o tempo
    # da ZARA realmente vai"; core/ipc_handlers.py is the documented voice
    # dispatcher (_process_voice_message/_speak_response); core/gemini_live_voice.py,
    # core/voice_tts.py, core/voice_stt.py and core/model_router.py are the
    # dedicated voice/latency owner files per .claude/rules/time-zara.md;
    # core/vigia_das_respostas.py and core/claude_brain.py explicitly discuss
    # response latency/completion.
    plausible = {
        'core/cronometro.py', 'core/ipc_handlers.py', 'core/gemini_live_voice.py',
        'core/voice_tts.py', 'core/voice_stt.py', 'core/model_router.py',
        'core/vigia_das_respostas.py', 'core/claude_brain.py',
    }
    assert set(result) & plausible, f'nenhum modulo plausivel de voz/latencia em {result}'


def test_a_different_natural_objective_resolves_to_memory_modules():
    """A different symptom family (memory/history) must not collapse to the
    same result as the voice/latency one - it should point somewhere else."""
    objective = ('a ZARA nao tem memoria, ela esquece tudo e nao lembra o que '
                 'eu falei antes')
    result = select_source_scope(WORKSPACE, objective)

    assert result, 'a queixa de memoria nao pode voltar vazia'
    for relative in result:
        assert (WORKSPACE / relative).is_file(), f'{relative} nao existe de verdade no disco'

    plausible = {
        'core/operational_recall.py', 'core/reminder_intent.py',
        'core/memoria_automatica.py', 'core/conversation_history.py',
        'core/obsidian_memory.py', 'core/actions/aprendizado_acoes.py',
        'memory/user_memory.py', 'memory/project_memory.py',
        'core/memory/contextual_memory.py', 'core/memory/conversation_memory.py',
    }
    assert set(result) & plausible, f'nenhum modulo plausivel de memoria em {result}'


def test_genuinely_unmappable_objective_refuses_honestly_in_portuguese():
    """No real module in this repository is 'about being prettier' - the
    mission must refuse instead of guessing a random file."""
    result = select_source_scope(WORKSPACE, 'Faca a ZARA ficar mais bonita.')
    assert result == []


def test_vague_objective_without_any_named_symptom_still_refuses():
    """Non-regression for the existing SourceMission test: an objective with
    no content word at all (only generic verbs/pronouns) must still refuse,
    not latch onto an incidental keyword match."""
    result = select_source_scope(WORKSPACE, 'Melhore a ZARA sem indicar assunto algum')
    assert result == []


def test_refusal_message_is_portuguese_and_readable_for_a_non_programmer():
    assert 'SOURCE_SCOPE_NOT_IDENTIFIED' not in SCOPE_NOT_IDENTIFIED_MESSAGE
    assert 'não consegui identificar' in SCOPE_NOT_IDENTIFIED_MESSAGE
    assert '.py' not in SCOPE_NOT_IDENTIFIED_MESSAGE
    assert 'concrete observed module' not in SCOPE_NOT_IDENTIFIED_MESSAGE


def test_scope_is_always_small():
    objective = ('QUERO QUE VOCE MELHORE O TEMPO DE RESPOSTA DA VOZ DA ZARA '
                 'ELA AINDA DEMORA MUITO DE ME RESPONDER')
    result = select_source_scope(WORKSPACE, objective)
    assert 1 <= len(result) <= 3


def test_near_instant_voice_response_request_targets_voice_pipeline():
    objective = '@artemis convoque o time trabalhe para que o tempo de resposta da voz da zara seja quase instantaneo'
    result = select_source_scope(WORKSPACE, objective)
    assert result == [
        'core/gemini_live_voice.py',
        'core/voice_tts.py',
        'core/model_router.py',
    ]
    assert all((WORKSPACE / relative).is_file() for relative in result)


def test_unverified_opencode_models_request_targets_model_integration():
    result = select_source_scope(WORKSPACE, 'corrija os modelos nao verificados da open code')
    assert result == [
        'core/lab_v1/providers/opencode.py',
        'core/lab_v1/front_brain.py',
        'core/lab_v1/providers/registry.py',
    ]
    assert all((WORKSPACE / relative).is_file() for relative in result)
