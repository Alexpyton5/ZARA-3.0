"""ZARA-APROVAR-DO-CELULAR-001 — a trava muda de lugar, não deixa de existir.

Alex, antes de dormir: *"se eu deixar o computador em casa, eu não vou poder
clicar nisso e a gente vai ficar com o projeto parado, não existe isso"*. 
Ele está certo, e o problema é real: hoje, quando algo precisa da autorização
dele, tudo para até ele voltar. Se ele sai às 8h e volta às 18h, foram dez horas
de nada — com o computador ligado, a ZARA acordada e nós dois esperando.

**O que NÃO fazer:** a ZARA aprovar sozinha. Aí a trava deixa de existir e ela
autoriza qualquer coisa, inclusive besteira minha. Trocar segurança por
conveniência aqui é o pior negócio possível, e é justamente o tipo de atalho que
este projeto passou meses evitando.

**O que fazer:** o pedido vai até ele. Chega no celular — *"o Claude quer fazer
X. Responde SIM ou NÃO"* — ele responde de onde estiver, e a ZARA age. A trava
continua inteira; só mudou de lugar, do mouse para o bolso dele.

Regras que não se negociam aqui:
- **Silêncio nunca é sim.** Sem resposta, o pedido morre por tempo.
- **Uma resposta serve a um pedido.** Nada de "sim" solto autorizando o que
  estiver na fila; ele responde citando, ou responde ao pedido mais recente e
  só a ele.
- **O pedido expira.** Um "sim" dado seis horas depois autoriza uma coisa que
  já não faz sentido.
"""

from __future__ import annotations

import itertools
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path


def config_dir() -> Path:
    """Return the config directory for API keys."""
    return Path.home() / "ZARA3" / "config"


# Tempo que um pedido fica de pé esperando resposta. Passou disso, morreu —
# porque autorização velha é autorização para outro contexto.
_VALIDADE = 6 * 60 * 60  # 6 horas

# Auditoria do Codex, achado 9: "ok", "beleza", "vai" e "faz" estavam aqui, e
# o comentário logo acima jurava que "um ok casual não autoriza nada". O código
# fazia o contrário do que o comentário prometia.
#
# O caso real: existe um pedido aberto para apagar builds; ele recebe outra
# mensagem qualquer do bot e responde "ok". A fila lia isso como autorização
# para apagar.
#
# Ficaram só as palavras que ninguém diz por reflexo. "Sim" é resposta; "ok" é
# acusar recebimento. Quem quiser aprovar com uma palavra ambígua ainda pode —
# citando o código do pedido, que é um ato deliberado.

_SIM = {
    "sim", "autorizo", "aprovado", "aprova", "aprovo",
    "pode sim", "sim pode", "confirmo", "confirmado", "libera", "liberado",
}

# Aceitas apenas quando ele CITA o código do pedido: aí a intenção é inequívoca.
_SIM_COM_CODIGO = _SIM | {
    "ok", "beleza", "pode", "manda", "manda ver", "vai", "faz", "faça", "faca",
    "claro", "positivo", "yes", "y", "s",
}

_NAO = {
    "nao", "não", "n", "nada", "para", "pare", "cancela", "cancelar", "negativo",
    "no", "recusa", "recusado", "nem pensar", "de jeito nenhum", "esquece",
}


def _limpar(texto: str) -> str:
    return " ".join(str(texto or "").split()).strip(" .!?,;:").casefold()


# Dois pedidos feitos no mesmo segundo têm o mesmo relógio, e então "o mais
# recente" vira sorteio — justamente na hora de decidir o que um "sim" solto
# autoriza. O contador desempata sem depender da precisão do relógio.

_ORDEM = itertools.count()


@dataclass
class Pedido:
    """Uma autorização esperando o Alex."""
    o_que: str
    quem_pediu: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:6])
    criado_em: float = field(default_factory=time.time)
    ordem: int = field(default_factory=lambda: next(_ORDEM))

    @property
    def vencido(self) -> bool:
        return (time.time() - self.criado_em) > _VALIDADE

    def como_pergunta(self) -> str:
        return (
            f"{self.quem_pediu} quer fazer isto:\n\n{self.o_que}\n\n"
            f"Responde SIM ou NÃO. (pedido {self.id})\n"
        )


class FilaDeAprovacao:
    """Os pedidos abertos, e a leitura honesta da resposta dele."""
    def __init__(self) -> None:
        self._abertos: dict[str, Pedido] = {}
        # Pedido já respondido não desaparece da consulta: quem pediu
        # (ex.: a ponte do Telegram) confere o status depois de resolvido,
        # e "sumiu da fila" não pode ser confundido com "nunca existiu".
        self._resolvidos: dict[str, str] = {}

    def pedir(self, o_que: str, quem_pediu: str = "O Claude") -> Pedido:
        self._faxina()
        pedido = Pedido(o_que=str(o_que or "").strip(), quem_pediu=quem_pediu)
        self._abertos[pedido.id] = pedido
        return pedido

    def abertos(self) -> list[Pedido]:
        self._faxina()
        # Mais novo primeiro: é a ele que um "sim" solto se refere.
        return sorted(self._abertos.values(), key=lambda p: p.ordem, reverse=True)

    def _faxina(self) -> None:
        for chave in [k for k, p in self._abertos.items() if p.vencido]:
            self._abertos.pop(chave, None)

    def responder(self, texto: str) -> tuple[Pedido | None, bool | None]:
        """Lê a resposta dele. Devolve (pedido, aprovado).

        `(None, None)` quer dizer que isto não era resposta de aprovação — é
        mensagem normal e segue o caminho de sempre. Tratar qualquer frase como
        resposta seria pior que não ter a fila: um "ok" casual autorizaria algo.
        """
        self._faxina()
        if not self._abertos:
            return None, None
        limpo = _limpar(texto)
        if not limpo:
            return None, None

        # Resposta citando o pedido: "sim 4f2a1c" ou "4f2a1c nao".
        alvo: Pedido | None = None
        for pedido in self._abertos.values():
            if pedido.id in limpo:
                alvo = pedido
                limpo = _limpar(limpo.replace(pedido.id, ""))
                break

        # Citar o código é um ato deliberado: ali um "ok" vale, porque ele
        # teve de olhar qual pedido estava respondendo. Sem código, só as
        # palavras que ninguém diz sem querer.
        aceitas = _SIM_COM_CODIGO if alvo is not None else _SIM
        veredito: bool | None = None
        if limpo in aceitas:
            veredito = True
        elif limpo in _NAO:
            veredito = False

        if veredito is None:
            # Ele escreveu outra coisa. Não é resposta — e um pedido continua
            # aberto esperando. Silêncio e assunto novo nunca viram permissão.
            return None, None

        if alvo is None:
            # Sem código citado: a resposta vale para o pedido mais recente,
            # como o contrato desta classe promete ("responde citando, ou
            # responde ao pedido mais recente e só a ele"). Sem isto, um
            # "sim" solto batia em `alvo=None` e explodia com AttributeError
            # — que a ponte engolia e virava "Não consegui", nunca aprovando
            # nada de verdade.
            alvo = max(self._abertos.values(), key=lambda p: p.ordem)

        self._abertos.pop(alvo.id, None)
        self._resolvidos[alvo.id] = "approved" if veredito else "rejected"
        return alvo, veredito

    def cancelar(self, id_do_pedido: str) -> bool:
        return self._abertos.pop(id_do_pedido, None) is not None

    def get_status(self, id_do_pedido: str) -> str | None:
        """Retorna o status do pedido: 'pending', 'approved', 'rejected', 'expired' ou None se não existe."""
        self._faxina()
        resolvido = self._resolvidos.get(id_do_pedido)
        if resolvido is not None:
            return resolvido
        pedido = self._abertos.get(id_do_pedido)
        if pedido is None:
            return None
        if pedido.vencido:
            return "expired"
        return "pending"