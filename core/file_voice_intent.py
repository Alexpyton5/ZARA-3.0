"""Closed natural-language intents for safe, known-folder file operations."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_FOLDERS = {
    "downloads": "downloads",
    "documentos": "documents",
    "documents": "documents",
    "corujão": "corujao",
    "corujao": "corujao",
}
_BASENAME = r"([\wÀ-ÿ .()_-]{1,120}\.[A-Za-z0-9]{1,12})"
_FOLDER = r"(downloads|documentos|documents|corujão|corujao)"
# ZARA-CRIAR-PASTA-001: nome de pasta nao tem extensao (diferente de _BASENAME),
# mas usa o mesmo charset restrito -- _clean_name ja recusa "..", "/" e "\\".
_FOLDER_NAME = r"([\wÀ-ÿ .()_-]{1,120})"


@dataclass
class FileIntent:
    action: str
    params: dict = field(default_factory=dict)
    mutating: bool = False


def _clean_name(value: str) -> str | None:
    name = " ".join(str(value or "").split())
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        return None
    return name


def detect_file_intent(text: str) -> FileIntent | None:
    raw = str(text or "").strip().strip(".!?")
    raw = re.sub(r"^zara\s*[,;:]?\s*", "", raw, flags=re.IGNORECASE)

    if re.fullmatch(
        r"(?:abra|abre|abrir)\s+(?:o\s+)?(?:último|ultimo)\s+(?:arquivo\s+)?(?:que\s+)?(?:eu\s+)?baixei",
        raw,
        re.IGNORECASE,
    ):
        return FileIntent("files_open_latest", {"folder": "downloads"})

    match = re.fullmatch(rf"(?:liste|mostre)\s+(?:os\s+)?arquivos\s+(?:em|de)\s+{_FOLDER}", raw, re.IGNORECASE)
    if match:
        return FileIntent("files_list", {"folder": _FOLDERS[match.group(1).casefold()]})

    match = re.fullmatch(rf"(?:procure|busque)\s+(.{{1,120}}?)\s+(?:nos\s+arquivos\s+)?(?:em|de)\s+{_FOLDER}", raw, re.IGNORECASE)
    if match:
        query = " ".join(match.group(1).split())
        return FileIntent("files_search", {"pattern": re.escape(query), "folder": _FOLDERS[match.group(2).casefold()]})

    match = re.fullmatch(rf"resuma\s+(?:o\s+)?arquivo\s+{_BASENAME}\s+(?:em|de)\s+{_FOLDER}", raw, re.IGNORECASE)
    if match:
        name = _clean_name(match.group(1))
        return FileIntent("files_text_summary", {"name": name, "folder": _FOLDERS[match.group(2).casefold()]}) if name else None

    match = re.fullmatch(rf"cri[ea]\s+(?:uma\s+)?pasta\s+(?:chamada\s+)?{_FOLDER_NAME}\s+em\s+{_FOLDER}", raw, re.IGNORECASE)
    if match:
        name = _clean_name(match.group(1))
        return FileIntent("files_create_folder", {"name": name, "folder": _FOLDERS[match.group(2).casefold()]}, True) if name else None

    match = re.fullmatch(rf"crie\s+(?:o\s+)?arquivo\s+{_BASENAME}\s+em\s+{_FOLDER}\s+com\s+(?:o\s+)?conteúdo\s+(.{{1,2000}})", raw, re.IGNORECASE)
    if match:
        name = _clean_name(match.group(1))
        return FileIntent("files_write", {"name": name, "folder": _FOLDERS[match.group(2).casefold()], "content": match.group(3)}, True) if name else None

    match = re.fullmatch(rf"adicione\s+(.{{1,2000}}?)\s+ao\s+arquivo\s+{_BASENAME}\s+em\s+{_FOLDER}", raw, re.IGNORECASE)
    if match:
        name = _clean_name(match.group(2))
        return FileIntent("files_write", {"name": name, "folder": _FOLDERS[match.group(3).casefold()], "content": match.group(1), "append": True}, True) if name else None

    match = re.fullmatch(rf"sobrescreva\s+(?:o\s+)?arquivo\s+{_BASENAME}\s+em\s+{_FOLDER}\s+com\s+(.{{1,2000}})", raw, re.IGNORECASE)
    if match:
        name = _clean_name(match.group(1))
        return FileIntent("files_write", {"name": name, "folder": _FOLDERS[match.group(2).casefold()], "content": match.group(3), "overwrite": True}, True) if name else None

    match = re.fullmatch(rf"renomeie\s+(?:o\s+)?arquivo\s+{_BASENAME}\s+para\s+{_BASENAME}\s+em\s+{_FOLDER}", raw, re.IGNORECASE)
    if match:
        old_name, new_name = _clean_name(match.group(1)), _clean_name(match.group(2))
        return FileIntent("files_rename", {"name": old_name, "new_name": new_name, "folder": _FOLDERS[match.group(3).casefold()]}, True) if old_name and new_name else None

    match = re.fullmatch(rf"(copie|mova)\s+(?:o\s+)?arquivo\s+{_BASENAME}\s+de\s+{_FOLDER}\s+para\s+{_FOLDER}", raw, re.IGNORECASE)
    if match:
        name = _clean_name(match.group(2))
        return FileIntent(
            "files_copy" if match.group(1).casefold() == "copie" else "files_move",
            {"name": name, "source_folder": _FOLDERS[match.group(3).casefold()], "destination_folder": _FOLDERS[match.group(4).casefold()]},
            True,
        ) if name else None

    match = re.fullmatch(rf"organize\s+{_FOLDER}\s+sem\s+apagar\s+nada", raw, re.IGNORECASE)
    if match:
        return FileIntent("files_organize_by_extension", {"folder": _FOLDERS[match.group(1).casefold()], "dry_run": False}, True)
    return None
