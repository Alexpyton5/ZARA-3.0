from core.actions import os_ops
from core.pc_voice_intent import PcVoiceIntentDetector


def test_type_text_preserves_original_unicode_and_case():
    text = "Zara, digite ‘Teste da ZARA com acentuação: ação, memória, coração.’"
    result = PcVoiceIntentDetector(pc_control_allowed=False).detect(text)
    assert result.action == "input_type_text"
    assert result.param == "Teste da ZARA com acentuação: ação, memória, coração."
    assert result.blocked is False


def test_hotkeys_are_closed_allowlist():
    assert PcVoiceIntentDetector().detect("selecione tudo").param == "select_all"
    assert PcVoiceIntentDetector().detect("cole aqui").param == "paste"
    assert os_ops.input_hotkey_action("alt_f4").success is False


def test_type_requires_safe_field(monkeypatch):
    monkeypatch.setattr(os_ops, "_focused_editable_field", lambda: None)
    result = os_ops.input_type_text_action("Olá")
    assert result.success is False
    assert result.data["status"] == "SAFE_FIELD_REQUIRED"


def test_sensitive_clipboard_is_never_pasted(monkeypatch):
    field = {"hwnd": 1, "pid": 2, "process": "notepad.exe"}
    monkeypatch.setattr(os_ops, "_focused_editable_field", lambda: field)
    monkeypatch.setattr(os_ops, "_uia_field_text", lambda field: "")
    monkeypatch.setattr("pyperclip.paste", lambda: "senha: SEGREDO_123")
    result = os_ops.input_hotkey_action("paste")
    assert result.success is False
    assert result.data["status"] == "BLOCKED_SAFETY"
