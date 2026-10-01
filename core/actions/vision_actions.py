"""Screen OCR actions layered on the existing capture implementation."""
from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

from core.action_registry import ActionResult, action
from core.actions import vision as _vision
from core.screen_understanding import describe_screen

_capture_raw = getattr(_vision.vision_screenshot_action, "__wrapped__", _vision.vision_screenshot_action)


def _temporary_capture_path() -> Path:
    from core.paths import user_data_dir

    folder = user_data_dir() / "cache" / "vision"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"screen-{uuid.uuid4().hex}.png"


def _capture(path: str = "", region: dict[str, int] | None = None, monitor: int = 0) -> ActionResult:
    target = Path(path).expanduser().resolve() if path else _temporary_capture_path()
    result = _capture_raw(region=region, path=str(target), monitor=monitor)
    if not result.success:
        return result
    if not target.exists() or target.stat().st_size == 0:
        return ActionResult(False, error="A captura nao foi encontrada depois de salvar")
    result.data = dict(result.data or {}, path=str(target))
    result.output = f"Captura salva e verificada em {target}"
    return result


@action(name="vision_screenshot", category="vision", description="Captura a tela e confirma o arquivo gerado")
def vision_screenshot_action(region: dict[str, int] | None = None, path: str = "", monitor: int = 0) -> ActionResult:
    return _capture(path, region, monitor)


def _ocr_words(image_path: str, lang: str) -> tuple[list[dict[str, Any]], str | None]:
    if not _vision.TESSERACT_AVAILABLE or not _vision.PIL_AVAILABLE:
        return [], "OCR indisponivel: Pillow/pytesseract nao estao instalados"
    try:
        image = _vision.Image.open(image_path)
        data = _vision.pytesseract.image_to_data(
            image, lang=lang, output_type=_vision.pytesseract.Output.DICT
        )
        words = []
        for index, raw in enumerate(data.get("text", [])):
            text = str(raw or "").strip()
            if not text:
                continue
            confidence_raw = data.get("conf", ["-1"])[index]
            try:
                confidence = float(confidence_raw)
            except (TypeError, ValueError):
                confidence = -1.0
            words.append({
                "text": text,
                "left": int(data["left"][index]), "top": int(data["top"][index]),
                "width": int(data["width"][index]), "height": int(data["height"][index]),
                "confidence": confidence,
            })
        return words, None
    except Exception as exc:
        return [], str(exc)


@action(name="vision_read_screen", category="vision", description="Le o texto da tela ou descreve visualmente a captura")
def vision_read_screen_action(question: str = "", lang: str = "por+eng", region: dict[str, int] | None = None) -> ActionResult:
    capture = _capture(region=region)
    if not capture.success:
        return capture
    path = str(capture.data["path"])
    if str(question or "").strip():
        description = describe_screen(path, question)
        if description is None:
            return ActionResult(False, error="Nao consegui interpretar a tela com o modelo visual")
        return ActionResult(True, description, data={"text": description, "path": path, "mode": "semantic"})
    words, error = _ocr_words(path, lang)
    if error:
        return ActionResult(False, error=f"Nao consegui ler a tela: {error}")
    text = " ".join(word["text"] for word in words).strip()
    return ActionResult(True, text or "Nenhum texto legivel encontrado.", data={"text": text, "words": words, "path": path})


def _find_matches(text: str, words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    needle = str(text or "").strip().casefold()
    if not needle:
        return []
    tokens = needle.split()
    matches = []
    for start in range(len(words)):
        candidate = words[start:start + len(tokens)]
        if len(candidate) != len(tokens):
            continue
        if [item["text"].casefold() for item in candidate] != tokens:
            continue
        left = min(item["left"] for item in candidate)
        top = min(item["top"] for item in candidate)
        right = max(item["left"] + item["width"] for item in candidate)
        bottom = max(item["top"] + item["height"] for item in candidate)
        matches.append({"text": " ".join(item["text"] for item in candidate), "left": left, "top": top,
                        "width": right - left, "height": bottom - top,
                        "confidence": min(item["confidence"] for item in candidate)})
    return matches


@action(name="vision_find_text", category="vision", description="Localiza texto visivel na tela")
def vision_find_text_action(text: str, lang: str = "por+eng", region: dict[str, int] | None = None) -> ActionResult:
    capture = _capture(region=region)
    if not capture.success:
        return capture
    words, error = _ocr_words(str(capture.data["path"]), lang)
    if error:
        return ActionResult(False, error=f"Nao consegui executar OCR: {error}")
    matches = _find_matches(text, words)
    if not matches:
        return ActionResult(False, error=f"Texto {text!r} nao encontrado na tela", data={"matches": []})
    offset_left = int((region or {}).get("left", 0))
    offset_top = int((region or {}).get("top", 0))
    for match in matches:
        match["left"] += offset_left
        match["top"] += offset_top
    return ActionResult(True, f"Texto encontrado {len(matches)} vez(es).", data={"matches": matches})


@action(name="vision_click_text", category="vision", risk="MEDIUM", capability="PC_CONTROL", description="Clica no centro de um texto encontrado por OCR")
def vision_click_text_action(text: str, occurrence: int = 0, lang: str = "por+eng") -> ActionResult:
    from core.actions.computer_use import _foreground, computer_click_action
    observed = _foreground()
    if observed is None:
        return ActionResult(False, error='Janela ativa indisponível.', verificado=False)
    found = getattr(vision_find_text_action, "__wrapped__", vision_find_text_action)(text=text, lang=lang)  # avoid a second registry gate
    if not found.success:
        return found
    matches = found.data["matches"]
    if occurrence < 0 or occurrence >= len(matches):
        return ActionResult(False, error="Ocorrencia solicitada nao existe")
    match = matches[occurrence]
    x = match["left"] + match["width"] // 2
    y = match["top"] + match["height"] // 2
    return computer_click_action(x, y, int(observed['hwnd']))


@action(name="vision_wait_for_text", category="vision", description="Aguarda texto aparecer na tela")
def vision_wait_for_text_action(text: str, timeout_seconds: float = 10.0, interval_seconds: float = 0.5, lang: str = "por+eng") -> ActionResult:
    timeout_seconds = max(0.1, min(float(timeout_seconds), 120.0))
    interval_seconds = max(0.1, min(float(interval_seconds), 5.0))
    deadline = time.monotonic() + timeout_seconds
    last_error = ""
    while time.monotonic() < deadline:
        found = getattr(vision_find_text_action, "__wrapped__", vision_find_text_action)(text=text, lang=lang)
        if found.success:
            return found
        last_error = found.error
        time.sleep(interval_seconds)
    return ActionResult(False, error=f"Tempo esgotado aguardando {text!r}. Ultima leitura: {last_error}")
