"""AUDITORIA_2026-08-27: TaskScheduler (core/actions/scheduler.py) ja existia
completo -- add/remove/list, loop de fundo, calculo de proximo horario --
mas nada no boot chamava .start(). Achado na limpeza de hoje: peca pronta,
nunca ligada. Modo 2 dos "3 modos" (na hora / agendado / vigiando sozinha)."""
from __future__ import annotations

import inspect

import core.ipc_handlers as ipc_handlers


def test_initialize_wires_and_starts_the_task_scheduler():
    source = inspect.getsource(ipc_handlers.IPCHandler.initialize)

    assert "TaskScheduler" in source
    assert "set_action_runner" in source
    assert ".start()" in source


def test_scheduler_actually_runs_a_task_end_to_end(tmp_path, monkeypatch):
    """Prova real, nao so leitura de codigo: agenda uma tarefa pra "agora" e
    confirma que ela executa sozinha, sem ninguem chamar de novo."""
    import time as time_module

    from core.actions.scheduler import TaskScheduler
    import core.actions  # noqa: F401 -- garante actions registradas
    from core.action_registry import get_registry

    monkeypatch.setattr(
        "core.actions.scheduler.user_data_dir", lambda: tmp_path
    )

    scheduler = TaskScheduler()
    scheduler.tasks.clear()
    scheduler.set_action_runner(lambda name, params: get_registry().execute(name, **params))
    scheduler.start()
    try:
        task_id = scheduler.add_task("teste", "system_time", {}, "once:2020-01-01T00:00:00")
        import datetime
        scheduler.tasks[task_id].next_run = datetime.datetime.now().isoformat()

        deadline = time_module.monotonic() + 12
        while time_module.monotonic() < deadline and scheduler.tasks[task_id].run_count == 0:
            time_module.sleep(0.5)

        assert scheduler.tasks[task_id].run_count == 1
    finally:
        scheduler.stop()
