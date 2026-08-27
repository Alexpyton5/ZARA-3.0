"""Core Actions Package — Auto-registers all actions on import."""
from __future__ import annotations

# Re-export registry
from core.action_registry import ActionResult, action, get_registry, registry

# Import all action modules to register them (trigger @action decorators)
from core.actions import (  # noqa: F401
    aprendizado_acoes,
    browser,
    code,
    files,
    media_apps,
    os_ops,
    ponte_claude,
    scheduler,
    system,
    terminal,
    vision,
    web,
    windows_radios,
)

def _load_plugins(plugins_dir=None) -> None:
    """ZARA-PLUGINS-2026-08-27: capacidade nova vira um arquivo solto em
    plugins/, sem precisar editar este arquivo nem reiniciar nada por engano
    de outro modulo. Cada arquivo usa o mesmo decorator @action de sempre.

    Um plugin quebrado (erro de sintaxe, import faltando, exception na
    importacao) fica marcado como BROKEN e o resto continua funcionando —
    inspirado no Mark LI (ideia publica, codigo escrito do zero aqui).
    """
    import importlib.util
    import sys
    from pathlib import Path

    if plugins_dir is None:
        plugins_dir = Path(__file__).resolve().parents[2] / "plugins"
    if not plugins_dir.is_dir():
        return

    for plugin_file in sorted(plugins_dir.glob("*.py")):
        if plugin_file.name.startswith("_"):
            continue
        module_name = f"zara_plugin_{plugin_file.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, plugin_file)
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            print(f"[Plugins] Carregado: {plugin_file.name}")
        except Exception as e:
            print(f"[Plugins] BROKEN {plugin_file.name}: {e}")


_load_plugins()

__all__ = [
    "registry",
    "get_registry",
    "ActionResult",
    "action",
]
