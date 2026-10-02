"""ZARA-WHATSAPP-001 — Alex comandando a ZARA pelo WhatsApp.

Missão pessoal da zoe (ordem direta do Alex, 02/10): tornar possível ele
falar com a zoe pelo WhatsApp dele e ela controlar o PC dele no que ele
disser.

**Por que este caminho.** O WhatsApp oficial (Business Cloud API) exige
conta de empresa, aprovação e cobra por mensagem (Meta) — VETADO, porque
API paga é vetada. O caminho não-oficial (bibliotecas de QR code) pode
derrubar o número — o risco é o telefone pessoal dele ser banido
(ver ZARA-TELEGRAM-001). Por isso este conector usa o TRANSPORTE
PONTE-ZOE: as mensagens trafegam pelo canal que a zoe já opera (pasta
`whatsapp-inbox/` na raiz do projeto — sem custo, sem risco de ban).
O transporte é plugável: se um dia o Alex escolher outro transporte
(oficial ou outro), basta implementar `TransporteWhatsApp`.

**Sem servidor e sem abrir porta.** A ZARA pergunta se há mensagem nova
(polling). Nada entra no computador por iniciativa de fora.

**Só ele fala.** Mensagem de qualquer remetente que não seja o dono é
ignorada. Sem isso, quem descobrisse o canal teria controle do PC dele.

**O portão continua mandando.** Este conector NÃO executa nada sozinho e
NÃO mexe no portão de grant do DEX (fail-closed, sem bypass): ele só
entrega (destino, conteúdo) ao `executar`, e é o pipeline existente —
com o portão — que decide se autoriza. Sem grant válido, nada de PC.

Fluxo das mensagens recebidas:

    "zara: ..."  -> comando para a própria ZARA
    "codex: ..." -> digita no Codex
    "claude: ..."-> digita no Claude
    qualquer outra -> tratada como comando da ZARA
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

_LIMITE_MENSAGEM = 3500  # folga para o prefixo; o resto fica no computador
_IDADE_MAXIMA = 60 * 60  # segundos; mais velho que isso não se executa sozinho
_JANELA_REPETICAO = 120  # não repetir a mesma resposta dentro deste intervalo
_INTERVAL_POLL = 5  # segundos entre uma checagem e outra


@dataclass
class MensagemWhatsApp:
    """Uma mensagem que chegou pelo canal do WhatsApp."""

    id: str
    remetente: str
    texto: str
    quando: float = field(default_factory=time.time)


class TransporteWhatsApp:
    """Interface plugável do canal físico.

    `buscar_novas(desde_id)` devolve as mensagens com id maior que
    `desde_id`, em ordem crescente. `enviar(destino, texto)` entrega a
    resposta ao dono. Ambos nunca explodem: falha devolve [] / False.
    """

    async def buscar_novas(self, desde_id: str) -> list[MensagemWhatsApp]:
        raise NotImplementedError

    async def enviar(self, destino: str, texto: str) -> bool:
        raise NotImplementedError


class TransportePastaLocal(TransporteWhatsApp):
    """Transporte padrão: arquivos JSON numa pasta local.

    Entrada: `<pasta>/entrada/*.json` com `{"id", "remetente", "texto",
    "quando"}`. Depois de lido, o arquivo vai para `<pasta>/processadas/`
    (auditoria — nada se perde). Saída: `<pasta>/saida/*.json`, que a
    zoe/relay recolhe e entrega pelo WhatsApp de verdade.

    É assim que o canal funciona hoje sem custo e sem risco de ban: a
    zoe deposita aqui o que ele mandou pelo WhatsApp, e recolhe daqui o
    que a ZARA respondeu.
    """

    def __init__(self, pasta: Path | None = None):
        if pasta is None:
            try:
                from core.paths import project_root

                pasta = project_root() / "whatsapp-inbox"
            except Exception:
                pasta = Path("whatsapp-inbox")
        self.pasta = Path(pasta)
        self.entrada = self.pasta / "entrada"
        self.saida = self.pasta / "saida"
        self.processadas = self.pasta / "processadas"

    def _garantir_pastas(self) -> bool:
        try:
            self.entrada.mkdir(parents=True, exist_ok=True)
            self.saida.mkdir(parents=True, exist_ok=True)
            self.processadas.mkdir(parents=True, exist_ok=True)
            return True
        except OSError:
            return False

    async def buscar_novas(self, desde_id: str) -> list[MensagemWhatsApp]:
        def _ler() -> list[MensagemWhatsApp]:
            achadas: list[MensagemWhatsApp] = []
            if not self._garantir_pastas():
                return achadas
            for arquivo in sorted(self.entrada.glob("*.json")):
                try:
                    dados = json.loads(arquivo.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                mid = str(dados.get("id") or arquivo.stem)
                if desde_id and mid <= desde_id:
                    continue
                achadas.append(
                    MensagemWhatsApp(
                        id=mid,
                        remetente=str(dados.get("remetente") or ""),
                        texto=str(dados.get("texto") or ""),
                        quando=float(dados.get("quando") or time.time()),
                    )
                )
                try:
                    arquivo.rename(self.processadas / arquivo.name)
                except OSError:
                    pass
            achadas.sort(key=lambda m: m.id)
            return achadas

        try:
            return await asyncio.to_thread(_ler)
        except Exception:
            return []

    async def enviar(self, destino: str, texto: str) -> bool:
        def _escrever() -> bool:
            if not self._garantir_pastas():
                return False
            nome = f"{int(time.time() * 1000)}-{destino}.json"
            try:
                (self.saida / nome).write_text(
                    json.dumps(
                        {"destino": destino, "texto": texto, "quando": time.time()},
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                return True
            except OSError:
                return False

        try:
            return await asyncio.to_thread(_escrever)
        except Exception:
            return False


class ConectorWhatsApp:
    """Recebe ordens do WhatsApp do Alex e devolve as respostas."""

    def __init__(
        self,
        executar: Callable[[str, str], Awaitable[str]],
        *,
        dono: str | None = None,
        transporte: TransporteWhatsApp | None = None,
    ):
        # executar(destino, texto) -> resposta em texto
        self.executar = executar
        # Aprendido na primeira mensagem: a partir daí, só este remetente é aceito.
        self.dono = (dono or "").strip() or None
        self.transporte = transporte or TransportePastaLocal()
        self._ultimo_id = ""
        self._parar = asyncio.Event()
        self._tarefa: asyncio.Task | None = None
        self._ultima_resposta = ("", 0.0)
        self._ultimo_sucesso = 0.0

    # ------------------------------------------------------------------
    @property
    def configurado(self) -> bool:
        return self.transporte is not None

    @staticmethod
    def _arquivo_marcador() -> Path | None:
        try:
            from core.paths import config_dir

            return config_dir() / "whatsapp_lido.json"
        except Exception:
            return None

    def _carregar_marcador(self) -> bool:
        """Devolve True se já havia marcador (ou seja: não é a primeira vez)."""
        arquivo = self._arquivo_marcador()
        if arquivo is None or not arquivo.exists():
            return False
        try:
            dados = json.loads(arquivo.read_text(encoding="utf-8"))
            self._ultimo_id = str(dados.get("ultimo_id") or "")
            if self.dono is None and dados.get("dono"):
                self.dono = str(dados["dono"])
        except Exception:
            return False
        return True

    def _gravar_marcador(self) -> None:
        arquivo = self._arquivo_marcador()
        if arquivo is None:
            return
        try:
            arquivo.parent.mkdir(parents=True, exist_ok=True)
            arquivo.write_text(
                json.dumps({"ultimo_id": self._ultimo_id, "dono": self.dono}),
                encoding="utf-8",
            )
        except Exception:
            pass  # perder o marcador atrasa, não quebra

    # ------------------------------------------------------------------
    async def iniciar(self) -> bool:
        if not self.configurado or self._tarefa is not None:
            return False
        primeira = not self._carregar_marcador()
        if primeira:
            # descarta o acumulado de forma assíncrona, sem travar a partida
            novas = await self.transporte.buscar_novas("")
            for msg in novas:
                if not self._ultimo_id or msg.id > self._ultimo_id:
                    self._ultimo_id = msg.id
            if self._ultimo_id:
                print(f"[WHATSAPP] acumulado antigo descartado ate {self._ultimo_id}", flush=True)
            self._gravar_marcador()
        self._parar.clear()
        self._ultimo_sucesso = time.time()
        self._tarefa = asyncio.create_task(self._escutar(), name="zara-whatsapp")
        print(f"[WHATSAPP] conector ligado (a partir de {self._ultimo_id or 'agora'})", flush=True)
        return True

    async def parar(self) -> None:
        self._parar.set()
        if self._tarefa:
            self._tarefa.cancel()
            self._tarefa = None

    # ------------------------------------------------------------------
    async def avisar(self, texto: str) -> bool:
        """Manda uma mensagem para o WhatsApp do Alex."""
        if not self.configurado or not self.dono:
            return False
        corpo = str(texto or "").strip()
        if not corpo:
            return False
        # Última trava anti-repetição: mesmo que algo dispare duas vezes,
        # ele não recebe a mesma frase duas vezes seguidas.
        anterior, quando = self._ultima_resposta
        agora = time.time()
        if corpo == anterior and (agora - quando) < _JANELA_REPETICAO:
            return True
        self._ultima_resposta = (corpo, agora)
        if len(corpo) > _LIMITE_MENSAGEM:
            corpo = corpo[:_LIMITE_MENSAGEM] + "\n\n[...] o resto está no computador."
        return await self.transporte.enviar(self.dono, corpo)

    # ------------------------------------------------------------------
    @staticmethod
    def rotear(texto: str) -> tuple[str, str]:
        """Descobre para quem é a mensagem. Devolve (destino, conteúdo)."""
        limpo = " ".join(str(texto or "").split())
        baixo = limpo.casefold()
        for nome, destino in (
            ("claude", "claude"),
            ("codex", "codex"),
            ("zara", "zara"),
            ("todos", "todos"),
            ("todo mundo", "todos"),
            ("galera", "todos"),
        ):
            if baixo.startswith(nome):
                resto = limpo[len(nome):].lstrip(" :,-—–.!?")
                return destino, resto
        return "zara", limpo

    # ------------------------------------------------------------------
    def _aceitar(self, msg: MensagemWhatsApp) -> bool:
        """Só o dono fala. Todo o resto é ignorado em silêncio."""
        if self.dono is None:
            # dono aprendido na primeira mensagem válida
            if msg.remetente:
                self.dono = msg.remetente
                self._gravar_marcador()
                return True
            return False
        return msg.remetente == self.dono

    async def _escutar(self) -> None:
        while not self._parar.is_set():
            try:
                novas = await self.transporte.buscar_novas(self._ultimo_id)
            except Exception:
                novas = []
            for msg in novas:
                if not self._ultimo_id or msg.id > self._ultimo_id:
                    self._ultimo_id = msg.id
                self._gravar_marcador()
                # mensagem velha demais não se executa sozinha
                if time.time() - msg.quando > _IDADE_MAXIMA:
                    continue
                if not msg.texto.strip():
                    continue
                if not self._aceitar(msg):
                    continue
                destino, conteudo = self.rotear(msg.texto)
                try:
                    resposta = await self.executar(destino, conteudo)
                except Exception as erro:
                    resposta = f"não consegui executar: {erro}"
                if resposta:
                    await self.avisar(str(resposta))
                self._ultimo_sucesso = time.time()
            try:
                await asyncio.wait_for(self._parar.wait(), timeout=_INTERVAL_POLL)
            except asyncio.TimeoutError:
                pass
