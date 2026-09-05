from core.actions import os_ops


def test_volume_clamps_and_succeeds_only_after_readback(monkeypatch):
    observed = iter((40, 100))
    writes = []
    monkeypatch.setattr(os_ops.platform, "system", lambda: "Windows")
    monkeypatch.setattr(os_ops, "_read_windows_volume", lambda: next(observed), raising=False)
    monkeypatch.setattr(
        os_ops,
        "_set_windows_volume",
        lambda level: writes.append(level) or True,
        raising=False,
    )
    monkeypatch.setattr(os_ops, "_mostrar_barrinha_de_volume", lambda level: True)

    result = os_ops.os_volume_action(150)

    assert result.success is True
    assert writes == [100]
    assert result.data == {
        "original_level": 40,
        "target_level": 100,
        "observed_level": 100,
        "verified": True,
    }


def test_volume_rejects_noop_without_writing(monkeypatch):
    writes = []
    monkeypatch.setattr(os_ops.platform, "system", lambda: "Windows")
    monkeypatch.setattr(os_ops, "_read_windows_volume", lambda: 40, raising=False)
    monkeypatch.setattr(
        os_ops,
        "_set_windows_volume",
        lambda level: writes.append(level) or True,
        raising=False,
    )

    result = os_ops.os_volume_action(40)

    assert result.success is False
    assert result.data == {"original_level": 40, "target_level": 40, "verified": True}
    assert writes == []


def test_volume_mute_delegates_to_verified_mute_action(monkeypatch):
    expected = os_ops.ActionResult(success=True, output="Mudo ativado.")
    calls = []
    monkeypatch.setattr(os_ops.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        os_ops,
        "_audio_mute_action",
        lambda desired: calls.append(desired) or expected,
    )

    result = os_ops.os_volume_action(mute=True)

    assert result is expected
    assert calls == [True]


def test_brightness_allows_explicit_readback_tolerance(monkeypatch):
    readings = iter((40, 52))
    monkeypatch.setattr(os_ops.platform, "system", lambda: "Windows")
    monkeypatch.setattr(os_ops, "_read_windows_brightness", lambda: next(readings))
    monkeypatch.setattr(os_ops, "_set_windows_brightness", lambda level: level == 50)

    result = os_ops.os_brightness_absolute_action(50)

    assert result.success is True
    assert result.data["target"] == 50
    assert result.data["observed"] == 52
    assert result.data["tolerance"] == 2


def test_brightness_rejects_observed_value_outside_tolerance(monkeypatch):
    readings = iter((40, 53))
    monkeypatch.setattr(os_ops.platform, "system", lambda: "Windows")
    monkeypatch.setattr(os_ops, "_read_windows_brightness", lambda: next(readings))
    monkeypatch.setattr(os_ops, "_set_windows_brightness", lambda level: level == 50)

    result = os_ops.os_brightness_absolute_action(50)

    assert result.success is False
    assert result.data == {
        "supported": True,
        "original": 40,
        "target": 50,
        "observed": 53,
        "backend": "ddcci",
        "tolerance": 2,
    }


def test_night_light_never_reports_cloudstore_only_success(monkeypatch):
    monkeypatch.setattr(os_ops.platform, "system", lambda: "Windows")
    monkeypatch.setattr(os_ops, "_luz_noturna_por_registro", lambda desired: os_ops.ActionResult(success=True))
    monkeypatch.setattr(os_ops, "_open_night_light_settings", lambda: True)
    monkeypatch.setattr(os_ops, "_find_night_light_toggle", lambda: None)

    result = os_ops.os_night_light_on_action()

    assert result.success is False
    assert result.data["safe_status"] == "NOT_SUPPORTED_SAFE"


def test_window_close_protects_any_zara_window(monkeypatch):
    monkeypatch.setattr(os_ops.platform, "system", lambda: "Windows")
    monkeypatch.setattr(os_ops, "_eligible_window", lambda hwnd: hwnd == 123)
    monkeypatch.setattr(os_ops, "_window_text", lambda hwnd: "ZARA 3.0")
    monkeypatch.setattr(os_ops, "_window_process_name", lambda hwnd: "python.exe")

    result = os_ops.window_close_action(hwnd=123)

    assert result.success is False
    assert result.data == {"hwnd": 123, "status": "PROTECTED"}
