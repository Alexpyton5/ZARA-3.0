"""FASE 2 PECA 4 (28/09/2026): o outro lado do loop do "cerebro pesado".

A PECA 2 escreve a PERGUNTA-ZOE-<id>.md na caixinha quando a escada de
motores esgota, e a zoe responde no turno vanguarda criando
RESPOSTA-ZOE-<id>.md. Mas nada lia a resposta de volta: o loop ficava
pela metade — a pergunta saia e a resposta morria na caixinha.

Esta peca fecha o loop: no inicio de cada turno, o runtime pergunta ao
leitor se ja chegou resposta para alguma escalacao pendente desta
(sessao, tarefa) — e, se chegou, a resposta entra no prompt do turno
como contexto. A missao que nenhum motor conseguiu rodar agora tem a
ajuda da zoe dentro do prompt.

Regras fail-closed:
- resposta ainda nao chegou: o turno segue normal, nada muda;
- resposta chegou: e entregue UMA vez (consumida), no proximo turno da
  MESMA (sessao, tarefa) — nunca para tarefa diferente;
- resposta vazia ou ilegivel = ainda nao chegou (nao consome);
- caixinha inacessivel = o turno segue normal (melhor esforco, nunca
  explode);
- a resposta entra como CONTEXTO no prompt: o turno continua sujeito a
  escada de motores e aos gates normais — nada e mascarado.

FASE 2 PECA 6 (28/09/2026): o loop sobrevive ao restart.
- `ask_zoe` agora grava `sessao:`/`tarefa:` no arquivo da pergunta;
  `restore_from_inbox()` varre a caixinha na subida do runtime e
  re-registra as escalacoes pendentes (perguntas sem resposta e respostas
  ainda nao consumidas). Arquivos antigos, sem o cabecalho, sao
  ignorados — nunca adivinhados.
- Ao entregar uma resposta, o par pergunta+resposta e arquivado em
  `ZOE-INBOX/entregues/` (casa limpa + prova de entrega: o que esta na
  pasta principal nunca foi entregue, entao o restore nunca entrega
  duas vezes). Arquivar e melhor esforco: se falhar, a entrega ja
  aconteceu e o journal registra.

Logica pura + leitura de arquivo; stdlib; custo/rede/quota zero.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

try:  # pacote core.* (app) ou import direto (testes flat)
    from core.lab_v1.zoe_brain import (
        ANSWER_PREFIX,
        QUESTION_PREFIX,
        inbox_dir,
        read_zoe_answer,
    )
except ImportError:  # pragma: no cover
    from .zoe_brain import (  # type: ignore
        ANSWER_PREFIX,
        QUESTION_PREFIX,
        inbox_dir,
        read_zoe_answer,
    )

# Teto do trecho injetado no prompt: resposta e ajuda, nao relatorio.
ANSWER_CHARS_MAX = 4000

# Para onde vai o par pergunta+resposta depois de entregue (casa limpa).
ARCHIVE_DIRNAME = "entregues"


class ZoeAnswerReader:
    """Registra as escalacoes pendentes e entrega cada resposta uma vez."""

    def __init__(self, clock: Optional[Callable[[], str]] = None) -> None:
        # qid -> (session_id, task_id, agent_id)
        self._pending: Dict[str, Tuple[str, Optional[str], str]] = {}
        self._delivered: set = set()
        self._journal: List[Dict[str, Any]] = []
        self._clock = clock or (lambda: "unknown")

    # --- internos ------------------------------------------------------
    def _log(self, evento: str, **campos: Any) -> None:
        entrada = {"ts": self._clock(), "evento": evento}
        entrada.update(campos)
        self._journal.append(entrada)

    @staticmethod
    def _clean_qid(qid: Any) -> Optional[str]:
        # Mesmo saneamento do read_zoe_answer: so digitos e hifen.
        q = "".join(c for c in str(qid or "") if c.isdigit() or c == "-").strip("-")
        return q or None

    @staticmethod
    def _parse_routing(path: Path) -> Optional[Tuple[str, str, Optional[str]]]:
        """Le o cabecalho legivel por maquina de uma PERGUNTA-ZOE.

        Devolve (qid, session_id, task_id) ou None se o arquivo nao tiver
        o cabecalho da PECA 6 (formato antigo) ou estiver inconsistente.
        `tarefa: -` significa escalacao sem tarefa (turno avulso).
        """
        try:
            nome = path.name
            miolo = nome[len(QUESTION_PREFIX):]
            if miolo.endswith(".md"):
                miolo = miolo[:-len(".md")]
            qid_arquivo = ZoeAnswerReader._clean_qid(miolo)
            linhas = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return None
        campos: Dict[str, str] = {}
        for linha in linhas:
            if not linha.strip():
                break  # fim do cabecalho: o corpo pode ter "TAREFA:" etc.
            if ":" not in linha:
                continue
            chave, _, valor = linha.partition(":")
            chave = chave.strip().lower()
            if chave in ("id", "sessao", "tarefa"):
                campos[chave] = valor.strip()
        qid = ZoeAnswerReader._clean_qid(campos.get("id"))
        sid = (campos.get("sessao") or "").strip()
        if not qid or qid != qid_arquivo or not sid:
            return None
        tid = (campos.get("tarefa") or "").strip()
        return qid, sid, (None if tid in ("", "-") else tid)

    def _archive_pair(self, qid: str) -> None:
        """Move o par pergunta+resposta para ZOE-INBOX/entregues/.

        Melhor esforco: a entrega ja aconteceu quando isto roda; se o
        arquivo ficar na pasta principal, o restore futuro pode
        re-registrar — o journal deixa a duplicata auditavel.
        """
        try:
            pasta = inbox_dir()
            destino = pasta / ARCHIVE_DIRNAME
            destino.mkdir(parents=True, exist_ok=True)
            for prefixo in (QUESTION_PREFIX, ANSWER_PREFIX):
                origem = pasta / f"{prefixo}{qid}.md"
                if origem.is_file():
                    origem.rename(destino / origem.name)
            self._log("arquivar", qid=qid, pasta=ARCHIVE_DIRNAME)
        except Exception as exc:
            self._log("arquivar_falhou", qid=qid, erro=str(exc)[:200])

    # --- API publica ---------------------------------------------------
    def register(
        self,
        qid: Any,
        *,
        session_id: Any,
        task_id: Any = None,
        agent_id: Any = "",
    ) -> bool:
        """Registra uma escalacao pendente. Devolve False se o qid for
        invalido, ja estiver pendente ou ja tiver sido entregue."""
        q = self._clean_qid(qid)
        sid = str(session_id or "").strip()
        if not q or not sid:
            return False
        if q in self._pending or q in self._delivered:
            return False
        self._pending[q] = (sid, task_id, str(agent_id or ""))
        self._log("registrar", qid=q, session_id=sid, task_id=task_id)
        return True

    def pending(self) -> List[str]:
        """Qids ainda aguardando resposta da zoe."""
        return sorted(self._pending)

    def delivered(self) -> List[str]:
        """Qids ja entregues (consumidos)."""
        return sorted(self._delivered)

    def restore_from_inbox(
        self, inbox: Any = None
    ) -> List[Tuple[str, Optional[str]]]:
        """Re-registra as escalacoes pendentes encontradas na caixinha.

        Para a subida do runtime depois de um restart: o _pending e em
        memoria e morreria com o processo, deixando perguntas sem resposta
        e respostas nao consumidas orfas. Varre PERGUNTA-ZOE-*.md, entende
        so o cabecalho da PECA 6 (sessao:/tarefa:) e re-registra cada uma.
        Devolve a lista de (session_id, task_id) restauradas — o runtime
        usa para realimentar o _zoe_escalated e nao gerar pergunta
        duplicada para a mesma tarefa. Idempotente: chamar duas vezes nao
        duplica nada. Nunca explode: caixinha inacessivel = lista vazia.
        """
        restauradas: List[Tuple[str, Optional[str]]] = []
        try:
            pasta = Path(inbox) if inbox else inbox_dir()
            if not pasta.is_dir():
                return restauradas
            arquivos = sorted(pasta.glob(f"{QUESTION_PREFIX}*.md"))
        except Exception:
            return restauradas
        for path in arquivos:
            parsed = self._parse_routing(path)
            if parsed is None:
                continue
            qid, sid, tid = parsed
            if qid in self._delivered:
                continue
            if self.register(qid, session_id=sid, task_id=tid,
                             agent_id="restore"):
                restauradas.append((sid, tid))
                self._log("restaurar", qid=qid, session_id=sid, task_id=tid)
        return restauradas

    def take_for(
        self, session_id: Any, task_id: Any = None
    ) -> Optional[Tuple[str, str]]:
        """Se a zoe ja respondeu a alguma escalacao pendente desta
        (sessao, tarefa), devolve (qid, resposta) e marca como entregue.
        Senao, devolve None. Melhor esforco: caixinha inacessivel nunca
        explode — o turno segue normal."""
        sid = str(session_id or "").strip()
        alvos = [
            q
            for q, (s, t, _a) in self._pending.items()
            if s == sid and t == task_id
        ]
        for q in sorted(alvos):
            try:
                answer = read_zoe_answer(q)
            except Exception:
                continue  # melhor esforco: tenta o proximo
            if not answer:
                continue  # ainda nao respondeu — nao consome
            answer = answer.strip()
            if len(answer) > ANSWER_CHARS_MAX:
                answer = (
                    answer[:ANSWER_CHARS_MAX]
                    + f"\n\n[...resposta cortada em {ANSWER_CHARS_MAX} chars]"
                )
            self._delivered.add(q)
            del self._pending[q]
            self._log(
                "entregar", qid=q, session_id=sid, task_id=task_id,
                chars=len(answer),
            )
            # FASE 2 PECA 6: par entregue sai da pasta principal — o que
            # fica na caixinha nunca foi entregue (restore nunca duplica).
            self._archive_pair(q)
            return q, answer
        return None

    def journal(self) -> List[Dict[str, Any]]:
        return list(self._journal)
