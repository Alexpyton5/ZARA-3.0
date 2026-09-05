"""ZARA-SYSTEM-STATS-001 (Alex, 2026-08-28)

Modulo independente de leitura pontual de CPU/RAM/bateria via psutil.
Isolado de proposito -- nao e um daemon, nao roda em loop, nao e chamado
por nenhum caminho de producao da Zara ainda.

Aviso honesto: `core/actions/system.py::system_metrics_action` (registrada
como a action "system_metrics") ja le CPU/RAM/bateria/disco/rede e ja esta
plugada no ActionRegistry e no pipeline de voz/texto. Este modulo NAO
substitui aquele -- e uma leitura mais simples e sem dependencia do
ActionRegistry, pensada como bloco solto pro "Copiloto do Windows" (ver
backlog do projeto), nao como segunda fonte de verdade para o que ja existe.
Se algum dia isto for plugado em producao, decidir junto com Alex se
consome `system_metrics_action` em vez de duplicar a leitura psutil.
"""
from __future__ import annotations

from dataclasses import dataclass

import psutil


@dataclass(frozen=True, slots=True)
class SystemSnapshot:
    cpu_percent: float
    ram_percent: float
    ram_used_gb: float
    ram_total_gb: float
    battery_percent: float | None
    battery_plugged: bool | None


def read_stats(cpu_interval: float = 0.1) -> SystemSnapshot:
    """Leitura pontual e sincrona. `cpu_interval` bloqueia por esse tempo
    (padrao psutil) pra medir CPU de verdade em vez de devolver 0.0 na
    primeira chamada do processo."""
    cpu_percent = psutil.cpu_percent(interval=cpu_interval)
    mem = psutil.virtual_memory()
    battery = psutil.sensors_battery()
    return SystemSnapshot(
        cpu_percent=float(cpu_percent),
        ram_percent=float(mem.percent),
        ram_used_gb=round(mem.used / (1024 ** 3), 2),
        ram_total_gb=round(mem.total / (1024 ** 3), 2),
        battery_percent=float(battery.percent) if battery is not None else None,
        battery_plugged=bool(battery.power_plugged) if battery is not None else None,
    )


if __name__ == "__main__":
    snap = read_stats()
    print(f"CPU: {snap.cpu_percent:.1f}%")
    print(f"RAM: {snap.ram_percent:.1f}% ({snap.ram_used_gb}GB / {snap.ram_total_gb}GB)")
    if snap.battery_percent is not None:
        estado = "carregando" if snap.battery_plugged else "na bateria"
        print(f"Bateria: {snap.battery_percent:.0f}% ({estado})")
    else:
        print("Bateria: nao detectada (desktop ou sem sensor)")
