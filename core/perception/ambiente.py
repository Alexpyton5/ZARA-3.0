"""Sensor de ambiente — a ZARA percebe o que está acontecendo em volta.

Sem isto ela responde igual às 3 da manhã com 4% de bateria e às 3 da tarde com
o Alex no meio de uma reunião. Contexto de ambiente é o que separa "assistente
que responde" de "assistente que entende a hora".

Três invariantes mandam neste arquivo, e as três nasceram de erro real:

1. **Nunca bloquear a voz.** Este módulo é lido no caminho de resposta. Nenhuma
   função aqui abre socket, espera rede ou dorme. Tudo que depende de internet
   (clima, alcance real da internet) é preenchido por uma thread de fundo e lido
   do cache; se nunca rodou, o valor é `None` — nunca uma espera.

2. **Nunca derrubar a ZARA.** Um sensor que falha vira `None`, não exceção. Não
   saber a bateria não pode custar a resposta inteira.

3. **`None` é "não sei", `False` é "não".** A versão anterior devolvia `False`
   para internet quando o teste falhava por qualquer motivo, e "sem internet"
   virava afirmação sem prova. Aqui os dois estados são distintos, e o resumo em
   texto simplesmente **omite** o que não foi medido em vez de escrever "N/A".

Dependências: só `psutil` (já no projeto) e biblioteca padrão. A versão anterior
importava `pygetwindow`, que não está instalado — o módulo inteiro morria no
import.
"""
from __future__ import annotations

import ctypes
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime

import psutil

_WINDOWS = sys.platform == "win32"

# Janela ativa e ociosidade mudam a cada segundo; a lista de processos é cara e
# muda devagar. TTLs diferentes para não pagar caro por informação estável.
_TTL_RAPIDO = 2.0
_TTL_PROCESSOS = 15.0
_TTL_CLIMA = 30 * 60.0
_TTL_INTERNET = 60.0

_cache: dict[str, tuple[float, object]] = {}
_atualizando: set[str] = set()
_trava = threading.Lock()


def _cacheado(chave: str, ttl: float, buscar):
    """Memoriza por `ttl` segundos. Se `buscar` falhar, devolve `None`.

    Só para sensor barato — medido nesta máquina, todos abaixo de 12 ms.
    """
    agora = time.monotonic()
    with _trava:
        item = _cache.get(chave)
        if item is not None and agora - item[0] < ttl:
            return item[1]
    try:
        valor = buscar()
    except Exception:
        valor = None
    with _trava:
        _cache[chave] = (agora, valor)
    return valor


def _cacheado_de_fundo(chave: str, ttl: float, buscar):
    """Igual ao `_cacheado`, mas **nunca** paga o custo na hora da resposta.

    Existe por uma medição, não por precaução: varrer a memória dos processos
    custa 300 ms nesta máquina. No `_cacheado` normal isso vira um travamento de
    300 ms no turno de voz que tiver o azar de encontrar o cache vencido — a
    gagueira que este arquivo inteiro promete não causar.

    Aqui, cache vencido devolve o valor velho na hora e manda uma thread buscar
    o novo para o turno seguinte. Saber que o Chrome está aberto há 15 segundos
    vale muito mais do que saber agora e atrasar a fala.
    """
    agora = time.monotonic()
    with _trava:
        item = _cache.get(chave)
        fresco = item is not None and agora - item[0] < ttl
        if not fresco and chave not in _atualizando:
            _atualizando.add(chave)
            disparar = True
        else:
            disparar = False

    if disparar:

        def buscar_e_guardar() -> None:
            try:
                valor = buscar()
            except Exception:
                valor = None
            with _trava:
                _cache[chave] = (time.monotonic(), valor)
                _atualizando.discard(chave)

        threading.Thread(
            target=buscar_e_guardar, name=f"ambiente-{chave}", daemon=True
        ).start()

    return item[1] if item is not None else None


def _limpar_cache() -> None:
    """Só para os testes: força a próxima leitura a medir de verdade."""
    with _trava:
        _cache.clear()
        _atualizando.clear()


# --------------------------------------------------------------------------
# Estruturas devolvidas
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Bateria:
    """`percentual is None` significa desktop sem bateria OU falha na leitura."""

    percentual: float | None = None
    na_tomada: bool | None = None
    minutos_restantes: int | None = None


@dataclass(frozen=True)
class Rede:
    """`interface_ativa` é local e instantâneo; `internet` exige a thread de fundo."""

    interface_ativa: bool | None = None
    internet: bool | None = None


@dataclass(frozen=True)
class Janela:
    titulo: str = ""
    processo: str = ""
    pid: int | None = None


@dataclass(frozen=True)
class Clima:
    descricao: str = ""
    temperatura_c: float | None = None
    sensacao_c: float | None = None
    umidade: int | None = None
    cidade: str = ""


@dataclass(frozen=True)
class Ambiente:
    """Retrato do entorno num instante. Tudo opcional: sensor cego vira `None`."""

    momento: str = ""
    hora: str = ""
    periodo: str = ""
    dia_semana: str = ""
    fuso: str = ""
    utc_offset: str = ""
    ocioso_segundos: float | None = None
    cpu_percent: float | None = None
    ram_percent: float | None = None
    ram_livre_gb: float | None = None
    bateria: Bateria = Bateria()
    rede: Rede = Rede()
    janela: Janela = Janela()
    processos: tuple[str, ...] = ()
    total_processos: int | None = None
    clima: Clima | None = None

    def para_dicionario(self) -> dict:
        """Formato JSON, para IPC/tela. `processos` vira lista."""
        dados = asdict(self)
        dados["processos"] = list(self.processos)
        return dados


# --------------------------------------------------------------------------
# Sensores individuais — nenhum levanta exceção, nenhum espera rede
# --------------------------------------------------------------------------

_DIAS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")


def _periodo_do_dia(hora: int) -> str:
    if 0 <= hora < 6:
        return "madrugada"
    if 6 <= hora < 12:
        return "manhã"
    if 12 <= hora < 18:
        return "tarde"
    return "noite"


def _relogio() -> dict:
    """Hora local COM fuso resolvido — `astimezone()` sem argumento pega o do SO."""
    agora = datetime.now().astimezone()
    offset = agora.strftime("%z")
    return {
        "momento": agora.isoformat(timespec="seconds"),
        "hora": agora.strftime("%H:%M"),
        "periodo": _periodo_do_dia(agora.hour),
        "dia_semana": _DIAS[agora.weekday()],
        "fuso": agora.tzname() or "",
        "utc_offset": f"{offset[:3]}:{offset[3:]}" if len(offset) == 5 else offset,
    }


class _LastInputInfo(ctypes.Structure):
    """Struct do `GetLastInputInfo` (user32). Só usada no Windows."""

    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def _ocioso_segundos() -> float | None:
    """Há quanto tempo ninguém toca em teclado/mouse. É o sinal de "Alex ocupado".

    O contador de ticks do Windows é de 32 bits e dá a volta a cada ~49 dias.
    Por isso `GetTickCount` (32 bits, igual ao `dwTime`) e subtração mascarada em
    32 bits: com `GetTickCount64` a conta fica errada depois da virada. E sem
    fixar o `restype` o ctypes lê o tick como inteiro COM sinal, e o valor vira
    negativo depois de 24,8 dias de máquina ligada.
    """
    if not _WINDOWS:
        return None
    info = _LastInputInfo()
    info.cbSize = ctypes.sizeof(info)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
        return None
    ctypes.windll.kernel32.GetTickCount.restype = ctypes.c_uint
    agora = ctypes.windll.kernel32.GetTickCount()
    return ((agora - info.dwTime) & 0xFFFFFFFF) / 1000.0


def _janela_focada() -> Janela | None:
    """Título e processo da janela em foco, via user32 — sem `pygetwindow`."""
    if not _WINDOWS:
        return None
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    tamanho = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(tamanho + 1)
    user32.GetWindowTextW(hwnd, buffer, tamanho + 1)
    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    processo = ""
    if pid.value:
        try:
            processo = psutil.Process(pid.value).name()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            processo = ""
    return Janela(titulo=buffer.value, processo=processo, pid=pid.value or None)


def _processos() -> dict:
    """Os aplicativos que mais pesam na máquina, por RAM.

    A versão anterior tentava listar "aplicativos abertos" e acabava devolvendo
    todo processo do sistema — inclusive serviço que o Alex nunca viu. Ordenar
    por memória e cortar em 8 dá a lista que corresponde ao que está aberto na
    tela, que é o que interessa para a resposta.
    """
    vistos: dict[str, int] = {}
    total = 0
    for proc in psutil.process_iter(["name", "memory_info"]):
        try:
            nome = proc.info["name"]
            memoria = proc.info["memory_info"]
            if not nome:
                continue
            total += 1
            vistos[nome] = vistos.get(nome, 0) + (memoria.rss if memoria else 0)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    maiores = sorted(vistos.items(), key=lambda par: par[1], reverse=True)[:8]
    return {"processos": tuple(nome for nome, _ in maiores), "total": total}


def _bateria() -> Bateria:
    energia = psutil.sensors_battery()
    if energia is None:
        return Bateria()
    restante = energia.secsleft
    minutos = None
    if restante is not None and restante >= 0:
        minutos = int(restante // 60)
    return Bateria(
        percentual=round(float(energia.percent), 1),
        na_tomada=bool(energia.power_plugged),
        minutos_restantes=minutos,
    )


def _interface_ativa() -> bool | None:
    """Existe placa de rede no ar? É leitura local: não manda um pacote sequer."""
    try:
        estados = psutil.net_if_stats()
    except Exception:
        return None
    for nome, estado in estados.items():
        if estado.isup and "loopback" not in nome.lower() and not nome.lower().startswith("lo"):
            return True
    return False


def _cpu_ram() -> dict:
    """`cpu_percent(interval=None)` não bloqueia: compara com a chamada anterior."""
    memoria = psutil.virtual_memory()
    return {
        "cpu_percent": psutil.cpu_percent(interval=None),
        "ram_percent": memoria.percent,
        "ram_livre_gb": round(memoria.available / (1024**3), 2),
    }


# --------------------------------------------------------------------------
# Clima e internet — SÓ na thread de fundo, nunca no caminho da resposta
# --------------------------------------------------------------------------

# Códigos WMO devolvidos pela Open-Meteo (grátis, sem chave, sem cadastro).
_WMO = {
    0: "céu limpo",
    1: "quase limpo",
    2: "parcialmente nublado",
    3: "nublado",
    45: "nevoeiro",
    48: "nevoeiro com geada",
    51: "garoa fraca",
    53: "garoa",
    55: "garoa forte",
    56: "garoa congelante",
    57: "garoa congelante forte",
    61: "chuva fraca",
    63: "chuva",
    65: "chuva forte",
    66: "chuva congelante",
    67: "chuva congelante forte",
    71: "neve fraca",
    73: "neve",
    75: "neve forte",
    77: "grãos de neve",
    80: "pancadas de chuva",
    81: "pancadas fortes",
    82: "pancadas muito fortes",
    85: "pancadas de neve",
    86: "pancadas de neve fortes",
    95: "tempestade",
    96: "tempestade com granizo",
    99: "tempestade com granizo forte",
}


def _clima_ligado() -> bool:
    return os.environ.get("ZARA_CLIMA", "1").strip().lower() not in {"0", "false", "nao", "não"}


def _buscar_json(url: str, timeout: float = 6.0):
    requisicao = urllib.request.Request(url, headers={"User-Agent": "ZARA/3.0"})
    with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:  # noqa: S310
        return json.loads(resposta.read().decode("utf-8"))


def _coordenadas() -> tuple[float, float, str] | None:
    """Coordenadas por variável de ambiente; sem isso, uma vez por IP.

    Pedir a localização por IP é impreciso e sai da máquina. Fica atrás de
    `ZARA_CLIMA=0`, e quem configurar `ZARA_CLIMA_LAT`/`LON` nunca dispara a
    consulta externa.
    """
    lat = os.environ.get("ZARA_CLIMA_LAT")
    lon = os.environ.get("ZARA_CLIMA_LON")
    if lat and lon:
        try:
            return float(lat), float(lon), os.environ.get("ZARA_CLIMA_CIDADE", "")
        except ValueError:
            return None
    dados = _buscar_json("https://ipapi.co/json/")
    if not dados or dados.get("latitude") is None:
        return None
    return float(dados["latitude"]), float(dados["longitude"]), dados.get("city") or ""


def atualizar_clima_agora() -> Clima | None:
    """Consulta a Open-Meteo e guarda no cache. **Faz rede — só chame de fundo.**"""
    if not _clima_ligado():
        return None
    local = _cacheado("coordenadas", 24 * 3600.0, _coordenadas)
    if not local:
        return None
    lat, lon, cidade = local
    try:
        dados = _buscar_json(
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat:.4f}&longitude={lon:.4f}"
            "&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code"
            "&timezone=auto"
        )
        atual = dados["current"]
        clima = Clima(
            descricao=_WMO.get(int(atual.get("weather_code", -1)), ""),
            temperatura_c=atual.get("temperature_2m"),
            sensacao_c=atual.get("apparent_temperature"),
            umidade=atual.get("relative_humidity_2m"),
            cidade=cidade,
        )
    except (urllib.error.URLError, OSError, KeyError, ValueError, TypeError):
        return None
    with _trava:
        _cache["clima"] = (time.monotonic(), clima)
    return clima


def _probar_internet() -> bool:
    """Alcance real da internet: uma conexão DNS curta, só na thread de fundo."""
    import socket

    try:
        socket.create_connection(("1.1.1.1", 53), timeout=3).close()
        return True
    except OSError:
        return False


def atualizar_internet_agora() -> bool:
    """Mede o alcance da internet e guarda no cache. **Faz rede — só de fundo.**"""
    alcance = _probar_internet()
    with _trava:
        _cache["internet"] = (time.monotonic(), alcance)
    return alcance


_monitor: threading.Thread | None = None


def iniciar_monitor_de_fundo() -> threading.Thread:
    """Liga a thread daemon que mantém clima e internet frescos no cache.

    Opcional de propósito: sem ela o módulo continua inteiro e offline, só com
    `clima` e `rede.internet` em `None` ("não sei"). Não é chamada no import
    porque import não deve abrir rede.
    """
    global _monitor
    if _monitor is not None and _monitor.is_alive():
        return _monitor

    def girar() -> None:
        while True:
            try:
                # Mantém a varredura cara sempre quente, para que nem o primeiro
                # turno depois do boot pegue a lista vazia.
                _cacheado_de_fundo("processos", _TTL_PROCESSOS, _processos)
                atualizar_internet_agora()
                atualizar_clima_agora()
            except Exception:
                pass
            time.sleep(_TTL_INTERNET)

    _monitor = threading.Thread(target=girar, name="ambiente-monitor", daemon=True)
    _monitor.start()
    return _monitor


def _do_cache(chave: str, ttl: float):
    """Lê valor da thread de fundo. Vencido ou ausente = `None` = "não sei"."""
    with _trava:
        item = _cache.get(chave)
    if item is None or time.monotonic() - item[0] > ttl:
        return None
    return item[1]


# --------------------------------------------------------------------------
# API pública
# --------------------------------------------------------------------------


def ler_ambiente() -> Ambiente:
    """Retrato do entorno agora. Não bloqueia, não faz rede, não levanta exceção."""
    relogio = _relogio()
    processos = _cacheado_de_fundo("processos", _TTL_PROCESSOS, _processos) or {}
    recursos = _cacheado("cpu_ram", _TTL_RAPIDO, _cpu_ram) or {}
    clima = _do_cache("clima", _TTL_CLIMA)
    return Ambiente(
        momento=relogio["momento"],
        hora=relogio["hora"],
        periodo=relogio["periodo"],
        dia_semana=relogio["dia_semana"],
        fuso=relogio["fuso"],
        utc_offset=relogio["utc_offset"],
        ocioso_segundos=_cacheado("ocioso", _TTL_RAPIDO, _ocioso_segundos),
        cpu_percent=recursos.get("cpu_percent"),
        ram_percent=recursos.get("ram_percent"),
        ram_livre_gb=recursos.get("ram_livre_gb"),
        bateria=_cacheado("bateria", _TTL_RAPIDO, _bateria) or Bateria(),
        rede=Rede(
            interface_ativa=_cacheado("interface", _TTL_RAPIDO, _interface_ativa),
            internet=_do_cache("internet", _TTL_INTERNET * 3),
        ),
        janela=_cacheado("janela", _TTL_RAPIDO, _janela_focada) or Janela(),
        processos=processos.get("processos", ()),
        total_processos=processos.get("total"),
        clima=clima if isinstance(clima, Clima) else None,
    )


def alex_esta_ocupado(limite_segundos: float = 90.0) -> bool | None:
    """Teclado/mouse em uso agora? Serve de freio para a ZARA não interromper.

    `None` quando não dá para medir (fora do Windows) — quem chama decide o que
    fazer com a dúvida, em vez de receber um "não está ocupado" inventado.
    """
    ocioso = _cacheado("ocioso", _TTL_RAPIDO, _ocioso_segundos)
    if ocioso is None:
        return None
    return ocioso < limite_segundos


def resumo_ambiente() -> str:
    """Uma linha em pt-BR para injetar no prompt.

    Só entra no texto o que foi medido. Sensor cego é omitido — encher o prompt
    de "N/A" gasta token e ensina o modelo a falar de coisa que ninguém apurou.
    """
    a = ler_ambiente()
    partes = [f"{a.dia_semana} {a.hora} ({a.periodo})"]
    if a.fuso or a.utc_offset:
        partes[0] += f", fuso {a.fuso or a.utc_offset}"
    if a.janela.titulo:
        alvo = a.janela.processo or "janela"
        partes.append(f"em foco: {a.janela.titulo[:60]} [{alvo}]")
    if a.processos:
        partes.append("abertos: " + ", ".join(a.processos[:4]))
    if a.bateria.percentual is not None:
        estado = "na tomada" if a.bateria.na_tomada else "na bateria"
        partes.append(f"bateria {a.bateria.percentual:.0f}% ({estado})")
    if a.cpu_percent is not None:
        partes.append(f"CPU {a.cpu_percent:.0f}%")
    if a.ram_percent is not None:
        partes.append(f"RAM {a.ram_percent:.0f}%")
    if a.rede.internet is True:
        partes.append("internet ok")
    elif a.rede.internet is False:
        partes.append("sem internet")
    if a.ocioso_segundos is not None and a.ocioso_segundos >= 90:
        partes.append(f"ocioso há {int(a.ocioso_segundos // 60)} min")
    if a.clima and a.clima.temperatura_c is not None:
        local = f" em {a.clima.cidade}" if a.clima.cidade else ""
        partes.append(f"clima{local}: {a.clima.descricao} {a.clima.temperatura_c:.0f}°C")
    return " | ".join(partes)


if __name__ == "__main__":
    print(resumo_ambiente())
    print()
    print(json.dumps(ler_ambiente().para_dicionario(), indent=2, ensure_ascii=False))
