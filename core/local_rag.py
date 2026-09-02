"""ZARA-LOCAL-RAG-001 (Alex, 2026-08-28). Peça isolada.

Indexação e busca LOCAL de arquivos (.txt/.md/.pdf) por relevância --
"RAG local" do backlog. Decisão deliberada: TF-IDF puro em Python, ZERO
dependência nova de embeddings/vetor (sentence-transformers, chromadb, faiss
não estão no projeto e não seriam justificados só por isto). TF-IDF é a
metade "retrieval" de RAG sem precisar de rede nem de modelo -- a metade
"generation" (perguntar a um LLM sobre os trechos achados) fica pra quem
consumir o resultado, não é responsabilidade deste módulo.

Reusa `tools.file_organizer.extract_text` pra PDF, em vez de duplicar a
extração.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

_WORD_RE = re.compile(r"[a-zà-úA-ZÀ-Ú0-9]+")
_SUPPORTED_SUFFIXES = {".txt", ".md", ".pdf"}


def _tokenize(text: str) -> list[str]:
    return [w.lower() for w in _WORD_RE.findall(text) if len(w) > 2]


@dataclass(frozen=True, slots=True)
class Document:
    path: str
    text: str


@dataclass(frozen=True, slots=True)
class LocalIndex:
    documents: tuple[Document, ...]
    _term_frequencies: tuple[Counter, ...]
    _doc_frequency: Counter


@dataclass(frozen=True, slots=True)
class SearchHit:
    path: str
    score: float
    snippet: str


def load_documents(directory: str, *, recursive: bool = True) -> list[Document]:
    """Carrega .txt/.md/.pdf de um diretório. Arquivo que não extrai texto
    (PDF escaneado sem OCR, por exemplo) é simplesmente ignorado -- não
    quebra o carregamento dos outros."""
    from tools.file_organizer import extract_text

    root = Path(directory)
    if not root.is_dir():
        return []

    pattern = "**/*" if recursive else "*"
    documents: list[Document] = []
    for path in root.glob(pattern):
        if not path.is_file() or path.suffix.lower() not in _SUPPORTED_SUFFIXES:
            continue
        text = extract_text(path)
        if text.strip():
            documents.append(Document(path=str(path), text=text))
    return documents


def build_index(documents: list[Document]) -> LocalIndex:
    term_frequencies = tuple(Counter(_tokenize(doc.text)) for doc in documents)
    doc_frequency: Counter = Counter()
    for tf in term_frequencies:
        doc_frequency.update(tf.keys())
    return LocalIndex(documents=tuple(documents), _term_frequencies=term_frequencies, _doc_frequency=doc_frequency)


def _snippet(text: str, terms: set[str], radius: int = 100) -> str:
    lower = text.lower()
    for term in terms:
        index = lower.find(term)
        if index != -1:
            start = max(0, index - radius)
            end = min(len(text), index + len(term) + radius)
            return text[start:end].strip()
    return text[: radius * 2].strip()


def query(index: LocalIndex, question: str, *, top_k: int = 5) -> list[SearchHit]:
    """Busca TF-IDF simples. [] se o índice estiver vazio ou a pergunta não
    tiver termo reconhecível -- nunca inventa um resultado."""
    terms = set(_tokenize(question))
    if not terms or not index.documents:
        return []

    n_docs = len(index.documents)
    scores: list[tuple[float, int]] = []
    for doc_index, tf in enumerate(index._term_frequencies):
        score = 0.0
        for term in terms:
            term_count = tf.get(term, 0)
            if term_count == 0:
                continue
            doc_freq = index._doc_frequency.get(term, 0)
            idf = math.log((n_docs + 1) / (doc_freq + 1)) + 1
            score += term_count * idf
        if score > 0:
            scores.append((score, doc_index))

    scores.sort(key=lambda item: item[0], reverse=True)
    hits: list[SearchHit] = []
    for score, doc_index in scores[:top_k]:
        doc = index.documents[doc_index]
        hits.append(SearchHit(path=doc.path, score=round(score, 4), snippet=_snippet(doc.text, terms)))
    return hits
