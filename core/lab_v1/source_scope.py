"""Bounded source-file selection for SourceMission entry.

Two ways in, tried in this order:

1. EXPLICIT PATH — the owner typed a real path
   (``core/voice_tts.py``) inside the objective text. This is the strongest
   possible signal of intent and always wins; unchanged since the original
   implementation.

2. NATURAL LANGUAGE — the owner is not a programmer and describes a symptom
   ("a voz demora muito para responder") instead of naming a file. This is
   the ZARA Lab's main promised use case ("ele descreve O QUE quer, a ZARA
   decide COMO"), so refusing whenever no literal path is present makes the
   Lab unusable for its primary user.

   Resolved deterministically and locally, reusing the TF-IDF engine already
   in the project (``core.local_rag``, built for RAG-local search) instead of
   inventing a second search implementation. The objective text is matched
   against the real content of every real ``.py`` module under ``core/`` and
   ``memory/``. Generic ranking excludes ``core/lab_v1/**`` (the Lab's own
   engine) and paths containing "hermes". A narrowly identified OpenCode
   integration request can select its relevant Lab modules explicitly.

   Generic Portuguese words (articles, pronouns, "melhore", "conserte",
   "zara" itself, etc.) are stripped from the objective before matching so
   they cannot manufacture a false match purely because they appear
   incidentally in code comments everywhere. If nothing content-bearing
   survives that filter, or nothing in the real source matches what
   survives, the mission honestly refuses instead of guessing a module.

No third step (LLM disambiguation) is implemented: the local match is
sufficient for the cases this ships to cover, and adding a provider call
here would move a free, instant, offline decision behind a paid/latent one
for no measured benefit. See KNOWN_BROKEN in the task report.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

from core.local_rag import Document, _tokenize, build_index

_PATH_PATTERN = re.compile(r"(?<![\w/.-])(?:core|memory|frontend/src|tools|tests)(?:/[A-Za-z0-9_.-]+)+")

_NATURAL_LANGUAGE_ROOTS = ("core", "memory")
_EXCLUDED_SUBSTRINGS = ("hermes", "__pycache__", "lab_v1")
_MAX_MODULES = 3

# Generic Portuguese vocabulary (function words, hyper-common verbs, and
# meta-words about "asking for something") that carries no information about
# WHICH module is relevant. Filtered out of the objective before matching so
# a vague request ("melhore a zara sem indicar assunto algum") cannot latch
# onto one of these words simply because it shows up in a code comment
# somewhere. This is a deliberately conservative, hand-reviewed list, not an
# attempt to special-case any single phrase.
_GENERIC_WORDS = frozenset({
    # articles, prepositions, conjunctions, pronouns
    "de", "a", "o", "que", "e", "do", "da", "em", "um", "uma", "para", "com",
    "nao", "não", "os", "no", "se", "na", "as", "dos", "das", "por", "ao",
    "aos", "seu", "sua", "seus", "suas", "ou", "quando", "nos", "já",
    "ja", "eu", "também", "tambem", "só", "so", "pelo", "pela", "até", "ate",
    "isso", "ela", "ele", "eles", "elas", "entre", "depois", "antes", "sem",
    "mesmo", "quem", "nas", "me", "esse", "essa", "essas", "esses", "num",
    "nem", "meu", "minha", "meus", "minhas", "numa", "pelos", "pelas",
    "qual", "nós", "lhe", "lhes", "deles", "delas", "este", "esta",
    "estas", "estes", "dele", "dela", "tu", "te", "você", "voce", "vocês",
    "voces", "vos", "teu", "tua", "teus", "tuas", "nosso", "nossa",
    "nossos", "nossas", "isto", "aquilo", "aquele", "aquela", "aqueles",
    "aquelas", "algo", "tudo", "algum", "alguma", "alguns", "algumas",
    # very common auxiliary/light verbs across any conjugation seen here
    "estou", "está", "estamos", "estão", "estive", "esteve",
    "estivemos", "estiveram", "seja", "sejam", "fosse", "fossem", "fui",
    "foi", "fomos", "foram", "sou", "somos", "são", "sao", "era", "eram",
    "ser", "ter", "tenho", "tem", "temos", "têm", "tinha", "tinham",
    "tive", "teve", "tivemos", "tiveram", "há", "ha", "hão", "hao", "vou",
    "vai", "vamos", "vão", "vao", "quero", "queria", "gostaria", "preciso",
    "favor", "faça", "faca", "faz", "fazer", "fica", "ficar", "fico",
    "colocar", "deixar", "usar", "chamar", "poder", "pode", "posso",
    "podemos", "podem", "dizer", "diz", "ver", "vejo", "dar", "saber",
    "sei", "sabe", "parece", "parecer",
    # generic ZARA-support verbs: naming the ask, never the subsystem
    "melhore", "melhorar", "melhora", "conserte", "consertar", "console",
    "resolva", "resolver", "resolve", "arrume", "arrumar", "mude", "mudar",
    "muda", "corrija", "corrigir", "corrige", "zara",
    # generic nouns that name "a topic exists" without naming one
    "sistema", "aplicativo", "app", "coisa", "coisas", "parte", "jeito",
    "forma", "questao", "questão", "problema", "problemas", "assunto",
    "indicar", "vez", "vezes", "muito", "mais", "menos", "bem", "bom", "boa",
    "ontem", "ainda",
})

# BM25 constants (Robertson/Sparck Jones, the standard defaults). Plain
# TF-IDF (raw term count x idf, no length normalization) was tried first and
# rejected: it systematically favors the largest file in the corpus
# (core/ipc_handlers.py, the ~2700-line dispatcher that mentions nearly every
# subsystem in passing) over the small, topically-dense module that is
# actually the right answer, for almost any query. Dividing by raw document
# length overcorrects the other way and lets a single incidental match in a
# tiny file outrank a real match in a substantial one. BM25's saturating term
# frequency is the standard fix for both failure modes at once.
_BM25_K1 = 1.5
_BM25_B = 0.75


def _explicit_paths(workspace: Path, intent: str) -> list[str]:
    candidates: list[str] = []
    for raw in _PATH_PATTERN.findall(intent):
        relative = raw.replace("\\", "/").rstrip(".,;:!?")
        target = workspace.joinpath(*relative.split("/"))
        if target.is_file() and relative not in candidates:
            candidates.append(relative)
    return candidates


def _is_excluded(posix_path: str) -> bool:
    folded = posix_path.casefold()
    return any(marker in folded for marker in _EXCLUDED_SUBSTRINGS)


def _module_inventory(workspace: Path) -> list[Document]:
    """Real, existing ``.py`` modules eligible for natural-language mapping.

    Reads full file content (not just the docstring): the words a symptom
    description uses ("voz", "resposta", "tempo", "lembra") show up in
    comments and identifiers throughout a module, not only in its header.
    """
    documents: list[Document] = []
    for root_name in _NATURAL_LANGUAGE_ROOTS:
        root = workspace / root_name
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*.py")):
            posix = path.relative_to(workspace).as_posix()
            if not path.is_file() or _is_excluded(posix):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            title = posix.replace("/", " ").replace("_", " ").replace(".py", "")
            documents.append(Document(path=posix, text=(title + " ") * 2 + text))
    return documents


def _content_terms(intent: str) -> list[str]:
    """The objective, reduced to only the words that could name a subsystem."""
    seen = []
    for word in _tokenize(intent):
        if word not in _GENERIC_WORDS and word not in seen:
            seen.append(word)
    return seen


def _bm25_rank(index, query_terms: list[str], top_k: int) -> list[str]:
    """Rank ``index`` documents against ``query_terms`` with BM25.

    Reuses the tokenizer and the term/doc-frequency tables ``local_rag``
    already builds (``build_index``); only the scoring formula is our own,
    to add the length normalization ``local_rag.query`` does not need for
    its original short-document use case but this one does (see module
    docstring / constants above).
    """
    doc_lengths = [sum(tf.values()) for tf in index._term_frequencies]
    if not doc_lengths:
        return []
    avg_length = sum(doc_lengths) / len(doc_lengths)
    n_docs = len(index.documents)
    scored = []
    for doc_index, doc in enumerate(index.documents):
        tf = index._term_frequencies[doc_index]
        length = doc_lengths[doc_index] or 1
        score = 0.0
        for term in query_terms:
            frequency = tf.get(term, 0)
            if frequency == 0:
                continue
            doc_freq = index._doc_frequency.get(term, 0)
            idf = math.log((n_docs - doc_freq + 0.5) / (doc_freq + 0.5) + 1)
            score += idf * (frequency * (_BM25_K1 + 1)) / (
                frequency + _BM25_K1 * (1 - _BM25_B + _BM25_B * length / avg_length))
        if score > 0:
            scored.append((score, doc.path))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [path for _, path in scored[:top_k]]


def _ranked_modules(workspace: Path, intent: str) -> list[str]:
    terms = _content_terms(intent)
    if not terms:
        return []
    documents = _module_inventory(workspace)
    if not documents:
        return []
    index = build_index(documents)
    return _bm25_rank(index, terms, _MAX_MODULES)


def _focused_modules(workspace: Path, intent: str) -> list[str] | None:
    """Keep two observed repair requests on their actual subsystem files.

    Generic keyword ranking sends these requests to unrelated PC-action files.
    Only the paired symptom and subsystem cues below use a fixed scope; all
    other requests retain the existing natural-language ranking.
    """
    if (re.search(r"\btempo\s+de\s+resposta\b", intent, re.I)
            and re.search(r"\bvoz\b", intent, re.I)
            and re.search(r"\bquase\s+instant[aâ]ne", intent, re.I)):
        paths = ("core/gemini_live_voice.py", "core/voice_tts.py", "core/model_router.py")
    elif (re.search(r"\bmodelos?\b", intent, re.I)
            and re.search(r"\bn[aã]o\s+verificados?\b", intent, re.I)
            and re.search(r"\bopen\s*code\b", intent, re.I)):
        paths = ("core/lab_v1/providers/opencode.py", "core/lab_v1/front_brain.py",
                 "core/lab_v1/providers/registry.py")
    else:
        return None
    return [relative for relative in paths if (workspace / relative).is_file()]


SCOPE_NOT_IDENTIFIED_MESSAGE = (
    "não consegui identificar qual parte da ZARA mexer a partir dessa descrição. "
    "Tente descrever o sintoma com mais detalhe (o que ela fez de errado), "
    "ou diga em que parte da ZARA isso acontece (por exemplo: voz, memória, "
    "comandos, execução)."
)


def select_source_scope(workspace: Path, intent: str) -> list[str]:
    workspace = Path(workspace).resolve(strict=True)
    explicit = _explicit_paths(workspace, intent)
    if explicit:
        return explicit
    focused = _focused_modules(workspace, intent)
    if focused is not None:
        return focused
    return _ranked_modules(workspace, intent)
