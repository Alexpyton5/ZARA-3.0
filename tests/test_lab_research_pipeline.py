"""NIGHT-05: real research pipeline persistence.

Proves the three invariants the module exists for:
1. a research cycle is persisted;
2. it is recoverable later (new ResearchPipeline instance, same DB file);
3. researching the same question twice does not create a second cycle
   (basic dedup) — whitespace/case differences included.

No network call happens here: these are the recorded results of research
already done for real (see docs handoff), not a live research run.
"""
from __future__ import annotations

import pytest

from core.lab_v1.research_pipeline import MAX_SOURCES_PER_CYCLE, ResearchPipeline
from core.lab_v1.store import LabStore

ONE_SOURCE = [{
    "source": "https://www.assemblyai.com/blog/voice-agent-architecture",
    "finding": "Production voice agents stream LLM output to TTS in sentence-sized "
               "chunks instead of waiting for the full response.",
    "evidence": "\"Send text to TTS in sentence-sized chunks rather than word-by-word "
                "(too many requests) or all-at-once (too much delay).\"",
    "relevance": "General technique for cascaded LLM+TTS pipelines; does not directly "
                 "apply to ZARA's Gemini Live native-audio session.",
    "limitation": "Assumes a separate text-generation and TTS step; ZARA's bottleneck "
                  "is a single native-audio model call, not a chunkable text stream.",
}]


@pytest.fixture()
def store(tmp_path):
    s = LabStore(tmp_path / "lab_v1.db")
    s.initialize()
    return s


def test_research_cycle_is_persisted_and_recoverable(store, tmp_path):
    pipeline = ResearchPipeline(store)
    question = "Como eliminar a viagem de audio descartada da Gemini Live em turnos de acao?"
    saved = pipeline.record_cycle(
        question, ONE_SOURCE,
        recommendation="precisa_mais_investigacao",
    )
    assert saved["id"].startswith("research:")
    assert saved["source_count"] == 1
    assert saved["recommendation"] == "PRECISA_MAIS_INVESTIGACAO"
    assert saved["sources"][0]["source"] == ONE_SOURCE[0]["source"]

    # Recoverable later: a *new* ResearchPipeline bound to the *same* on-disk
    # DB file must see the row a previous process instance wrote.
    reopened_store = LabStore(tmp_path / "lab_v1.db")
    reopened_store.initialize()
    reopened_pipeline = ResearchPipeline(reopened_store)
    recovered = reopened_pipeline.get_cycle(question)
    assert recovered is not None
    assert recovered["id"] == saved["id"]
    assert recovered["sources"] == saved["sources"]

    by_id = reopened_pipeline.get_by_id(saved["id"])
    assert by_id == recovered


def test_duplicate_question_does_not_create_a_new_cycle(store):
    pipeline = ResearchPipeline(store)
    question = "Como eliminar a viagem de audio descartada da Gemini Live em turnos de acao?"
    first = pipeline.record_cycle(question, ONE_SOURCE, recommendation="precisa_mais_investigacao")
    # Same question, different whitespace/case, and *different* source payload:
    # the second call must be ignored — dedup is on the question, not the sources.
    second = pipeline.record_cycle(
        "  COMO eliminar a VIAGEM de audio   descartada da Gemini Live em turnos de acao?  ",
        [{**ONE_SOURCE[0], "finding": "a completely different finding"}],
        recommendation="implementar",
        implementation_candidate="isto nao deveria ser gravado",
    )
    assert second["id"] == first["id"]
    assert second["recommendation"] == first["recommendation"] == "PRECISA_MAIS_INVESTIGACAO"
    assert second["sources"] == first["sources"]
    assert len(pipeline.list_cycles()) == 1


def test_source_budget_is_enforced(store):
    pipeline = ResearchPipeline(store)
    too_many = [ONE_SOURCE[0]] * (MAX_SOURCES_PER_CYCLE + 1)
    with pytest.raises(ValueError, match="SOURCE_BUDGET_EXCEEDED"):
        pipeline.record_cycle("Pergunta com fontes demais", too_many,
                              recommendation="precisa_mais_investigacao")


def test_implementar_requires_a_candidate(store):
    pipeline = ResearchPipeline(store)
    with pytest.raises(ValueError, match="IMPLEMENTATION_CANDIDATE_REQUIRED"):
        pipeline.record_cycle("Pergunta sem candidato", ONE_SOURCE, recommendation="implementar")


def test_source_fields_are_required(store):
    pipeline = ResearchPipeline(store)
    incomplete = [{"source": "https://example.com", "finding": "x"}]
    with pytest.raises(ValueError, match="SOURCE_FIELD_REQUIRED"):
        pipeline.record_cycle("Pergunta com fonte incompleta", incomplete,
                              recommendation="precisa_mais_investigacao")
