"""
ZARA Lab — A caixinha: recados entre os 11 assentos via arquivos.

Protocolo (alicerce da Fase A "LAB VIVO"): os assentos conversam por uma
pasta compartilhada. Cada recado é um arquivo JSON; quem vai ler RECLAMA
(claim) o recado primeiro — ninguém processa o mesmo recado duas vezes,
ninguém perde recado, e a ordem de chegada é a ordem de verdade.

Regras:
- de/para: um dos 11 assentos; "TODOS" = recado aberto (cada assento
  reclama a sua cópia, sem briga).
- tipo: RECADO | PERGUNTA | RESPOSTA | ALERTA.
- conteudo: texto, de 1 a 64 KB. Caixinha é recado, não relatório.
- RESPOSTA exige o correlation_id do recado original (o fio não se perde).
- reclamar() é idempotente pro mesmo assento; assento errado no recado
  direto recebe ERRO (não lê recado dos outros).
- Tudo vira journal com relógio injetável (auditável, testes sem hora).

Lógica pura: sem rede, sem modelo, custo zero. Os arquivos vivem numa
pasta comum — o Lab do futuro pluga isso no fluxo (puxa → processa →
arquiva); o "quebrou, volta atrás" mora no portão de autoupdate.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


ASSENTOS = (
    "CEO", "ARCHITECT", "UI_DESIGNER", "ENGINEER", "SCRIBE",
    "REVIEWER", "CRITIC", "SECRETARY", "TESTER", "RESEARCHER", "PACKAGER",
)
BROADCAST = "TODOS"

TIPOS = ("RECADO", "PERGUNTA", "RESPOSTA", "ALERTA")

CONTEUDO_MAX = 64 * 1024  # 64 KB: recado, não relatório


class DropboxError(Exception):
    """Qualquer recado ilegal ou transição inválida cai aqui."""


def _check_assento(nome: Any, papel: str) -> str:
    if not isinstance(nome, str):
        raise DropboxError(f"{papel} precisa ser texto, veio {nome!r}")
    nome = nome.strip().upper()
    if nome not in ASSENTOS and nome != BROADCAST:
        raise DropboxError(f"{papel} inválido: {nome!r} (assento ou TODOS)")
    return nome


def _check_tipo(tipo: Any) -> str:
    if not isinstance(tipo, str):
        raise DropboxError(f"tipo precisa ser texto, veio {tipo!r}")
    tipo = tipo.strip().upper()
    if tipo not in TIPOS:
        raise DropboxError(f"tipo inválido: {tipo!r} (vale {', '.join(TIPOS)})")
    return tipo


def _check_conteudo(conteudo: Any) -> str:
    if not isinstance(conteudo, str) or not conteudo.strip():
        raise DropboxError("conteudo não pode ser vazio")
    conteudo = conteudo.strip()
    if len(conteudo) > CONTEUDO_MAX:
        raise DropboxError(
            f"conteudo passou do limite ({len(conteudo)} > {CONTEUDO_MAX} chars) "
            "— caixinha é recado, não relatório"
        )
    return conteudo


@dataclass
class Recado:
    seq: int                       # ordem de chegada (desempate/auditoria)
    msg_id: str                    # "MSG-0001"
    de: str                        # assento remetente
    para: str                      # assento ou TODOS
    tipo: str                      # RECADO | PERGUNTA | RESPOSTA | ALERTA
    conteudo: str
    correlation_id: Optional[str] = None
    reclamado_por: List[str] = field(default_factory=list)


class Dropbox:
    """A caixinha do Lab. Um dono por leitura, ordem garantida."""

    def __init__(self, pasta: Any, clock: Optional[Callable[[], str]] = None) -> None:
        self._pasta = str(pasta)
        os.makedirs(self._pasta, exist_ok=True)
        self._clock = clock or (lambda: "unknown")
        self._journal: List[Dict[str, Any]] = []

    # --- internos -----------------------------------------------------
    def _seq_path(self) -> str:
        return os.path.join(self._pasta, "seq.txt")

    def _proximo_seq(self) -> int:
        path = self._seq_path()
        atual = 0
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                atual = int(f.read().strip() or "0")
        proximo = atual + 1
        with open(path, "w", encoding="utf-8") as f:
            f.write(str(proximo))
        return proximo

    def _msg_path(self, msg_id: str) -> str:
        return os.path.join(self._pasta, f"{msg_id}.json")

    def _salvar(self, recado: Recado) -> None:
        # escreve em temp + rename: outro processo nunca vê arquivo pela metade
        dados = {
            "seq": recado.seq,
            "msg_id": recado.msg_id,
            "de": recado.de,
            "para": recado.para,
            "tipo": recado.tipo,
            "conteudo": recado.conteudo,
            "correlation_id": recado.correlation_id,
            "reclamado_por": recado.reclamado_por,
        }
        fd, tmp = tempfile.mkstemp(dir=self._pasta, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(dados, f, ensure_ascii=False)
            os.replace(tmp, self._msg_path(recado.msg_id))
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    def _carregar(self, msg_id: str) -> Recado:
        path = self._msg_path(msg_id)
        if not os.path.exists(path):
            raise DropboxError(f"recado não existe: {msg_id!r}")
        with open(path, "r", encoding="utf-8") as f:
            dados = json.load(f)
        return Recado(
            seq=dados["seq"],
            msg_id=dados["msg_id"],
            de=dados["de"],
            para=dados["para"],
            tipo=dados["tipo"],
            conteudo=dados["conteudo"],
            correlation_id=dados.get("correlation_id"),
            reclamado_por=list(dados.get("reclamado_por", [])),
        )

    def _log(self, evento: str, **campos: Any) -> None:
        entrada = {"ts": self._clock(), "evento": evento}
        entrada.update(campos)
        self._journal.append(entrada)

    # --- API pública ---------------------------------------------------
    def depositar(
        self,
        de: Any,
        para: Any,
        tipo: Any,
        conteudo: Any,
        correlation_id: Optional[str] = None,
    ) -> Recado:
        """Deixa um recado na caixinha. Devolve o recado registrado."""
        de = _check_assento(de, "de")
        para = _check_assento(para, "para")
        if de == BROADCAST:
            raise DropboxError("remetente não pode ser TODOS")
        tipo = _check_tipo(tipo)
        conteudo = _check_conteudo(conteudo)
        if tipo == "RESPOSTA" and not correlation_id:
            raise DropboxError("RESPOSTA exige correlation_id do recado original")
        seq = self._proximo_seq()
        recado = Recado(
            seq=seq,
            msg_id=f"MSG-{seq:04d}",
            de=de,
            para=para,
            tipo=tipo,
            conteudo=conteudo,
            correlation_id=correlation_id,
        )
        self._salvar(recado)
        self._log("depositar", msg_id=recado.msg_id, de=de, para=para, tipo=tipo)
        return recado

    def pendentes(self, para: Any) -> List[Recado]:
        """Recados que este assento ainda não reclamou, em ordem de chegada."""
        para = _check_assento(para, "para")
        if para == BROADCAST:
            raise DropboxError("TODOS não reclama recado — cada assento reclama o seu")
        achados: List[Recado] = []
        for nome in sorted(os.listdir(self._pasta)):
            if not nome.endswith(".json"):
                continue
            recado = self._carregar(nome[:-5])
            enderecado = recado.para == para or recado.para == BROADCAST
            if enderecado and para not in recado.reclamado_por:
                achados.append(recado)
        achados.sort(key=lambda r: r.seq)
        return achados

    def reclamar(self, msg_id: str, por: Any) -> Recado:
        """Reserva o recado pra este assento processar. Idempotente."""
        por = _check_assento(por, "por")
        if por == BROADCAST:
            raise DropboxError("TODOS não reclama recado")
        recado = self._carregar(msg_id)
        if recado.para != BROADCAST and recado.para != por:
            raise DropboxError(
                f"recado {msg_id} é de {recado.de} para {recado.para} — "
                f"{por} não pode ler recado dos outros"
            )
        if por not in recado.reclamado_por:
            recado.reclamado_por.append(por)
            self._salvar(recado)
            self._log("reclamar", msg_id=msg_id, por=por)
        return recado

    def responder(self, msg_id: str, de: Any, conteudo: Any) -> Recado:
        """Responde um recado mantendo o fio (correlation_id)."""
        de = _check_assento(de, "de")
        original = self._carregar(msg_id)
        conteudo = _check_conteudo(conteudo)
        resposta = self.depositar(
            de=de,
            para=original.de,
            tipo="RESPOSTA",
            conteudo=conteudo,
            correlation_id=original.msg_id,
        )
        return resposta

    def fio(self, correlation_id: str) -> List[Recado]:
        """Todos os recados do fio (original + respostas), em ordem."""
        achados: List[Recado] = []
        for nome in sorted(os.listdir(self._pasta)):
            if not nome.endswith(".json"):
                continue
            recado = self._carregar(nome[:-5])
            if recado.msg_id == correlation_id or recado.correlation_id == correlation_id:
                achados.append(recado)
        achados.sort(key=lambda r: r.seq)
        return achados

    def journal(self) -> List[Dict[str, Any]]:
        """Tudo que aconteceu na caixinha, com hora. Auditável."""
        return list(self._journal)
