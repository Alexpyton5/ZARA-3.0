from unittest.mock import AsyncMock

import pytest

from core.actions import os_ops
from core.ipc_handlers import IPCHandler
from core.pc_voice_intent import PcVoiceIntentDetector


@pytest.mark.parametrize(
    ("phrase", "action", "param"),
    [
        ("brilho em 50%", "os_brightness_absolute", "50"),
        ("coloque o brilho em 30", "os_brightness_absolute", "30"),
        ("deixe a tela em 25%", "os_brightness_absolute", "25"),
        ("aumente o brilho", "os_brightness_up", "up"),
        ("um pouco mais claro", "os_brightness_up", "up"),
        ("mais claro", "os_brightness_up", "up"),
        ("diminua o brilho", "os_brightness_down", "down"),
        ("um pouco mais escuro", "os_brightness_down", "down"),
        ("mais escuro", "os_brightness_down", "down"),
        ("ative a luz noturna", "os_night_light_on", "on"),
        ("desative a luz noturna", "os_night_light_off", "off"),
    ],
)
def test_brightness_and_night_light_phrases(phrase, action, param):
    result = PcVoiceIntentDetector(pc_control_allowed=True).detect(phrase)

    assert result.is_pc_intent is True
    assert result.action == action
    assert result.param == param


def test_absolute_brightness_clamps_and_verifies(monkeypatch):
    states = iter((40, 100))
    writes = []
    monkeypatch.setattr(os_ops.platform, "system", lambda: "Windows")
    monkeypatch.setattr(os_ops, "_read_windows_brightness", lambda: next(states))
    monkeypatch.setattr(os_ops, "_set_windows_brightness", lambda level: writes.append(level) or True)

    result = os_ops.os_brightness_absolute_action(150)

    assert result.success is True
    assert writes == [100]
    assert result.data == {
        "supported": True,
        "original": 40,
        "target": 100,
        "observed": 100,
        "backend": "ddcci",
    }


def test_absolute_brightness_falls_back_to_wmi_when_no_ddcci(monkeypatch):
    """Laptop panels expose no DDC/CI: the WMI backend must take over."""
    writes = []
    monkeypatch.setattr(os_ops.platform, "system", lambda: "Windows")
    monkeypatch.setattr(os_ops, "_read_windows_brightness", lambda: None)
    monkeypatch.setattr(os_ops, "_wmi_read_brightness", lambda: 90)
    monkeypatch.setattr(os_ops, "_wmi_set_brightness", lambda level: writes.append(level) or True)

    result = os_ops.os_brightness_absolute_action(90)

    assert result.success is True
    assert writes == [90]
    assert result.data["backend"] == "wmi"
    assert result.data["observed"] == 90


def test_get_brightness_falls_back_to_wmi_and_reports_observed(monkeypatch):
    monkeypatch.setattr(os_ops.platform, "system", lambda: "Windows")
    monkeypatch.setattr(os_ops, "_read_windows_brightness", lambda: None)
    monkeypatch.setattr(os_ops, "_wmi_read_brightness", lambda: 40)

    result = os_ops.os_brightness_action()

    assert result.success is True
    assert result.data == {"level": 40, "observed": 40}


def test_absolute_brightness_unsupported_when_no_backend(monkeypatch):
    monkeypatch.setattr(os_ops.platform, "system", lambda: "Windows")
    monkeypatch.setattr(os_ops, "_read_windows_brightness", lambda: None)
    monkeypatch.setattr(os_ops, "_wmi_read_brightness", lambda: None)

    result = os_ops.os_brightness_absolute_action(50)

    assert result.success is False
    assert result.data == {"supported": False}


@pytest.mark.parametrize(("start", "delta", "expected"), [(95, 10, 100), (5, -10, 0), (50, 10, 60), (50, -10, 40)])
def test_relative_brightness_uses_real_reference_and_clamps(monkeypatch, start, delta, expected):
    monkeypatch.setattr(os_ops.platform, "system", lambda: "Windows")
    monkeypatch.setattr(os_ops, "_read_windows_brightness", lambda: start)
    observed = []
    monkeypatch.setattr(os_ops, "_brightness_action", lambda level: observed.append(level) or os_ops.ActionResult(success=True))

    result = os_ops._relative_brightness(delta)

    assert result.success is True
    assert observed == [expected]


def test_relative_brightness_without_hardware_reference_is_explicit(monkeypatch):
    monkeypatch.setattr(os_ops.platform, "system", lambda: "Windows")
    monkeypatch.setattr(os_ops, "_read_windows_brightness", lambda: None)
    monkeypatch.setattr(os_ops, "_wmi_read_brightness", lambda: None)

    result = os_ops.os_brightness_up_action()

    assert result.success is False
    assert result.data == {"supported": False}
    assert "Não há referência" in result.error


class _FakeToggle:
    """Duble de controle acessível com TogglePattern."""

    def __init__(self, state, applies=True, toggle_ok=True):
        self.state = state
        self.applies = applies
        self.toggle_ok = toggle_ok
        self.toggles = 0

    def get_toggle_state(self):
        return self.state

    def toggle(self):
        self.toggles += 1
        if not self.toggle_ok:
            return False
        if self.applies and self.state is not None:
            self.state = not self.state
        return True


def _patch_night_light(monkeypatch, control):
    opened = []
    monkeypatch.setattr(os_ops.platform, "system", lambda: "Windows")
    monkeypatch.setattr(os_ops, "_open_night_light_settings", lambda: opened.append(True) or True)
    monkeypatch.setattr(os_ops, "_find_night_light_toggle", lambda *a, **k: control)
    monkeypatch.setattr(os_ops.time, "sleep", lambda _s: None)
    # ZARA-LUZ-NOTURNA-SILENCIOSA-001: estes testes cobrem a ROTA RESERVA (o app
    # Configurações). A rota rápida por registro é desligada aqui de propósito,
    # senão ela atenderia primeiro e o caminho de reserva nunca seria exercido —
    # e é justamente ele que precisa continuar honesto quando a rápida falhar.
    monkeypatch.setattr(os_ops, "_luz_noturna_por_registro", lambda _desejado: None)
    return opened


def test_night_light_on_verifies_pre_and_post_state(monkeypatch):
    control = _FakeToggle(False)
    opened = _patch_night_light(monkeypatch, control)

    result = os_ops.os_night_light_on_action()

    assert result.success is True
    assert control.toggles == 1
    assert opened == [True]
    assert result.data == {"supported": True, "before": False, "after": True, "changed": True}


def test_night_light_off_verifies_pre_and_post_state(monkeypatch):
    control = _FakeToggle(True)
    _patch_night_light(monkeypatch, control)

    result = os_ops.os_night_light_off_action()

    assert result.success is True
    assert result.data == {"supported": True, "before": True, "after": False, "changed": True}


def test_night_light_already_in_desired_state_does_not_toggle(monkeypatch):
    control = _FakeToggle(True)
    _patch_night_light(monkeypatch, control)

    result = os_ops.os_night_light_on_action()

    assert result.success is True
    assert control.toggles == 0
    assert result.data["changed"] is False


def test_night_light_fails_when_control_not_found(monkeypatch):
    _patch_night_light(monkeypatch, None)

    result = os_ops.os_night_light_on_action()

    assert result.success is False
    assert result.data["safe_status"] == "NOT_SUPPORTED_SAFE"
    assert "controle acessível" in result.error


def test_night_light_fails_when_state_not_readable(monkeypatch):
    control = _FakeToggle(None)
    _patch_night_light(monkeypatch, control)

    result = os_ops.os_night_light_on_action()

    assert result.success is False
    assert control.toggles == 0
    assert result.data["safe_status"] == "NOT_SUPPORTED_SAFE"


def test_night_light_fails_when_post_state_not_confirmed(monkeypatch):
    control = _FakeToggle(False, applies=False)
    _patch_night_light(monkeypatch, control)
    monkeypatch.setattr(os_ops.time, "sleep", lambda _s: None)

    result = os_ops.os_night_light_on_action()

    assert result.success is False
    assert control.toggles == 1
    assert result.data == {"supported": True, "before": False, "after": False, "changed": False}


def test_night_light_fails_when_toggle_refused(monkeypatch):
    control = _FakeToggle(False, toggle_ok=False)
    _patch_night_light(monkeypatch, control)

    result = os_ops.os_night_light_on_action()

    assert result.success is False
    assert result.data["changed"] is False
    assert "recusou" in result.error


def test_manual_button_control_reads_state_from_accessible_name():
    class _Elem:
        def __init__(self, name):
            self.CurrentName = name

    class _Invoke:
        def __init__(self):
            self.calls = 0

        def Invoke(self):
            self.calls += 1

    assert os_ops._ManualButtonControl(_Elem("Ativar agora"), _Invoke()).get_toggle_state() is False
    assert os_ops._ManualButtonControl(_Elem("Desativar agora"), _Invoke()).get_toggle_state() is True
    assert os_ops._ManualButtonControl(_Elem("Turn on now"), _Invoke()).get_toggle_state() is False
    assert os_ops._ManualButtonControl(_Elem("qualquer coisa"), _Invoke()).get_toggle_state() is None

    invoke = _Invoke()
    assert os_ops._ManualButtonControl(_Elem("Ativar agora"), invoke).toggle() is True
    assert invoke.calls == 1


def test_night_light_nunca_usa_clique_por_coordenada():
    """Coordenada de tela é frágil: muda com resolução, idioma e tema.

    A proibição original juntava duas coisas diferentes — clique cego E
    registro. Clique cego continua proibido. Registro passou a ser permitido
    (ZARA-LUZ-NOTURNA-SILENCIOSA-001) porque Alex pediu que nada abrisse na
    tela, e porque a leitura do registro é verificável: dá para conferir o
    resultado, coisa que um clique às cegas não permite.
    """
    import inspect

    fontes = (
        inspect.getsource(os_ops._night_light_set)
        + inspect.getsource(os_ops._find_night_light_toggle)
        + inspect.getsource(os_ops._luz_noturna_por_registro)
    )
    for proibido in ("SetCursorPos", "mouse_event", "click("):
        assert proibido not in fontes


def test_luz_noturna_confirma_o_resultado_antes_de_dizer_que_fez():
    """A regra que a proibição antiga realmente protegia: nada de falso sucesso.

    Escrever no registro e anunciar vitória sem reler seria exatamente a mentira
    que este projeto combate. A rota rápida tem de reler o estado.
    """
    import inspect

    fonte = inspect.getsource(os_ops._luz_noturna_por_registro)
    assert "_luz_noturna_ler()" in fonte
    assert "return None" in fonte  # desiste em vez de fingir que deu certo


def test_luz_noturna_desiste_quando_o_formato_e_desconhecido(monkeypatch):
    """Windows futuro pode mudar o blob. Nesse caso, cair para a rota antiga."""
    monkeypatch.setattr(os_ops, "_luz_noturna_ler", lambda: bytearray(b"\x00" * 43))

    assert os_ops._luz_noturna_por_registro(True) is None


def test_luz_noturna_nao_mexe_quando_ja_esta_no_estado_pedido(monkeypatch):
    ligada = bytearray(b"\x00" * 18 + b"\x15" + b"\x00" * 24)
    escritas = []
    monkeypatch.setattr(os_ops, "_luz_noturna_ler", lambda: bytearray(ligada))

    resultado = os_ops._luz_noturna_por_registro(True)

    assert resultado is not None
    assert resultado.success is True
    assert resultado.data["changed"] is False
    assert escritas == []


@pytest.mark.asyncio
async def test_local_brightness_executes_without_supercerebro(monkeypatch):
    execute = AsyncMock(return_value=type(
        "Result", (), {
            "success": True,
            "error": "",
            "output": "Brilho definido para 50%.",
            "data": {"observed": 50},
        }
    )())
    handler = IPCHandler(AsyncMock())
    monkeypatch.setattr("core.action_registry.execute_action", execute)

    reply = await handler._try_pc_intent("brilho em 50%")

    assert reply == "Brilho definido para 50%."
    execute.assert_awaited_once_with("os_brightness_absolute", level=50)


@pytest.mark.asyncio
async def test_ipc_clamps_absolute_brightness_before_closed_action(monkeypatch):
    calls = []

    async def fake_execute_action(action, **params):
        calls.append((action, params))
        return type(
            "Result",
            (),
            {
                "success": True,
                "error": "",
                "output": "Brilho definido para 100%.",
                "data": {"observed": 100},
            },
        )()

    handler = IPCHandler(AsyncMock())
    handler._set_supercerebro_state(True)
    monkeypatch.setattr("core.action_registry.execute_action", fake_execute_action)

    reply = await handler._try_pc_intent("brilho em 150%")

    assert calls == [("os_brightness_absolute", {"level": 100})]
    assert reply == "Brilho definido para 100%."
    assert handler._last_brightness_level == 100


@pytest.mark.parametrize("phrase", ["brilho && powershell", "hackeie a luz noturna", "execute os_brightness_up"])
def test_brightness_never_maps_arbitrary_text(phrase):
    result = PcVoiceIntentDetector(pc_control_allowed=True).detect(phrase)
    assert result.action not in {
        "os_brightness_absolute",
        "os_brightness_up",
        "os_brightness_down",
        "os_night_light_on",
        "os_night_light_off",
    }
    assert result.physical_effect == 0
