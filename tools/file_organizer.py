"""ZARA-FILE-ORGANIZER-001 (Alex, 2026-08-28). Peça isolada.

`files_move`/`files_rename`/`files_organize_by_extension`/`files_search`
(core/actions/files.py) já existem e já são gated (capability, allowlist de
pasta) -- este módulo só decide O QUE sugerir, olhando o CONTEÚDO real do
arquivo (não só a extensão), igual `tools/git_assistant.py` só sugere
commit. `plan_reorganization` NUNCA move nem renomeia nada -- devolve um
plano; quem executa é o pipeline real, com os gates que já existem.

Classificação por palavra-chave, determinística, sem IA -- suficiente pros
casos comuns (conta, recibo, contrato) e auditável. Se não reconhecer,
devolve categoria 'desconhecido' em vez de chutar.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_CATEGORY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("conta_luz", ("energia elétrica", "kwh", "distribuidora", "conta de luz")),
    ("conta_agua", ("saneamento", "consumo de água", "hidrômetro")),
    ("fatura_cartao", ("fatura", "cartão de crédito", "limite disponível")),
    ("recibo", ("recibo", "comprovante de pagamento")),
    ("contrato", ("contrato", "cláusula", "partes contratantes")),
    ("nota_fiscal", ("nota fiscal", "nfe", "cnpj emitente")),
)

_MONTHS_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho",
    7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}


@dataclass(frozen=True, slots=True)
class FilePlan:
    original_path: str
    suggested_name: str | None
    category: str
    confidence: str  # "alta" | "baixa" | "nenhuma"


def extract_text(path: Path) -> str:
    """Extrai texto de .txt/.md diretamente, ou de .pdf via pypdf. Formato
    não suportado (imagem escaneada sem OCR, .docx etc) devolve string
    vazia -- quem chamar trata como 'não deu pra ler', nunca como erro."""
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ""
    if suffix == ".pdf":
        try:
            import pypdf
            reader = pypdf.PdfReader(str(path))
            return "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception:
            return ""
    return ""


def classify_content(text: str) -> tuple[str, str]:
    """Devolve (categoria, confiança). 'desconhecido'/'nenhuma' quando
    nenhuma palavra-chave bate -- nunca inventa categoria."""
    lower = text.lower()
    if not lower.strip():
        return "desconhecido", "nenhuma"
    for category, keywords in _CATEGORY_KEYWORDS:
        hits = sum(1 for kw in keywords if kw in lower)
        if hits >= 2:
            return category, "alta"
        if hits == 1:
            return category, "baixa"
    return "desconhecido", "nenhuma"


def _extract_month_year(text: str) -> str | None:
    match = re.search(r"\b(0?[1-9]|1[0-2])[/-](20\d{2})\b", text)
    if match:
        month, year = int(match.group(1)), match.group(2)
        return f"{_MONTHS_PT.get(month, str(month))}_{year}"
    return None


def plan_reorganization(paths: list[str] | list[Path]) -> list[FilePlan]:
    """Analisa cada arquivo e devolve um plano de renomeação/categorização.
    NÃO move nem renomeia nada -- só propõe."""
    plans: list[FilePlan] = []
    for raw_path in paths:
        path = Path(raw_path)
        if not path.is_file():
            plans.append(FilePlan(str(path), None, "arquivo_nao_encontrado", "nenhuma"))
            continue

        text = extract_text(path)
        category, confidence = classify_content(text)
        suggested = None
        if confidence != "nenhuma":
            period = _extract_month_year(text)
            base = category.replace("_", " ").title().replace(" ", "_")
            suggested = f"{base}_{period}{path.suffix}" if period else f"{base}{path.suffix}"
        plans.append(FilePlan(str(path), suggested, category, confidence))
    return plans
