"""Teste capstone CONVERSA-UNICA: 4 fios, 1 thread (backend).

Prova, contra os modulos REAIS do app, que tudo o que o Alex ve
(texto digitado, voz falada, respostas da zoe pela ponte Conselheira
e resumo do Lab) cai no MESMO ConversationHistory — o fio unico.

Nota honesta sobre `engine`: no app, `_append_conversation_message`
(ipc_handlers.py) passa o `engine` do pipeline adiante sem tocar
(verificado no codigo em 28/09). Este teste espelha esse funil: o que
o chamador passa e o que o fio guarda — verbatim, sem duplicata.
"ponte-zoe" e "lab-resumo" sao os engines reais dos dois modulos
da zoe; "texto"/"voz" sao rotulos de cenario para os dois caminhos
que ja existiam no app.

Nota 2: `ConversationHistory.append` recebe `engine` como
keyword-only — por isso os turnos (role, conteudo, engine) sao
desempacotados de forma explicita, nunca com `append(*turno)`.

Logica local, stdlib + sqlite, zero custo/rede/quota.
"""

import os
import tempfile
import unittest

try:  # dentro do app (pacote core.*)
    from core.conversation_history import ConversationHistory
    from core.conselheira_history_bridge import (
        ENGINE_PONTE_ZOE,
        incoming_turns,
        outgoing_turn,
    )
    from core.lab_history_digest import (
        ENGINE_LAB_RESUMO,
        MAX_LINHAS_FIO,
        assinatura,
        digest_brief_text,
        digest_relatorio,
    )
except ImportError:  # teste flat
    from conversation_history import ConversationHistory
    from conselheira_history_bridge import (
        ENGINE_PONTE_ZOE,
        incoming_turns,
        outgoing_turn,
    )
    from lab_history_digest import (
        ENGINE_LAB_RESUMO,
        MAX_LINHAS_FIO,
        assinatura,
        digest_brief_text,
        digest_relatorio,
    )

BRIEF_CURTO = """BOLETIM DO CICLO 7
FEITO:
- voz: 15/15 testes verdes
ESTADO:
- loop: RUNNING
DECISÃO PEDIDA: nenhuma"""

BRIEF_LONGO = "BOLETIM DO CICLO 8\n" + "\n".join(
    ["FEITO:", "- fase 1 fechada"]
    + [f"ESTADO:\n- linha de estado {i}" for i in range(40)]
    + ["DECISÃO PEDIDA: aprovar o push"]
)


class _RelatorioMudo:
    """Relatorio que NAO passa no portao do modo silencioso."""

    def pode_falar(self):
        return False

    def formatar(self):
        return "isso nao deveria entrar"


def _history():
    fd, caminho = tempfile.mkstemp(suffix=".sqlite3")
    os.close(fd)
    os.unlink(caminho)  # ConversationHistory cria do zero
    return ConversationHistory(path=caminho)


def _guardar(history, turno):
    """Guarda um turno (role, conteudo, engine) no fio, como o app faz."""
    role, conteudo, engine = turno
    return history.append(role, conteudo, engine=engine)


def _fio(history):
    return history.list_recent(200)


class TestConversaUnicaIntegracao(unittest.TestCase):
    def test_quatro_fios_um_so_thread(self):
        h = _history()
        # 1. texto digitado (caminho que ja existia no app)
        h.append("user", "ZARA, abre a pasta Downloads", engine="texto")
        # 2. voz: fala do Alex + resposta falada (mesmo funil)
        h.append("user", "e aumenta o volume", engine="voz")
        h.append("assistant", "Volume no maximo.", engine="voz")
        # 3. ponte da Conselheira (modulo REAL da zoe)
        turno_ida = outgoing_turn({"text": "me lembra da reuniao as 15h"})
        self.assertEqual(turno_ida[2], ENGINE_PONTE_ZOE)
        _guardar(h, turno_ida)
        turnos_volta = incoming_turns(
            {"replies": [{"reply": "Lembrete criado: reuniao as 15h."}]}
        )
        self.assertEqual(len(turnos_volta), 1)
        _guardar(h, turnos_volta[0])
        # 4. resumo do Lab (modulo REAL da zoe)
        resumo = digest_brief_text(BRIEF_CURTO)
        self.assertEqual(resumo[2], ENGINE_LAB_RESUMO)
        _guardar(h, resumo)

        fio = _fio(h)
        self.assertEqual(len(fio), 6)
        self.assertEqual(
            [m["engine"] for m in fio],
            ["texto", "voz", "voz", "ponte-zoe", "ponte-zoe", "lab-resumo"],
        )
        self.assertEqual(
            [m["role"] for m in fio],
            ["user", "user", "assistant", "user", "assistant", "assistant"],
        )
        # Ordem cronologica (mais antigo primeiro) — e um fio so.
        self.assertTrue(
            fio[0]["content"].startswith("ZARA, abre")
            and fio[-1]["content"].startswith("BOLETIM DO CICLO 7")
        )

    def test_digest_idempotente_mesmo_ciclo_nao_duplica(self):
        h = _history()
        vistos = set()
        for _ in range(2):  # o mesmo boletim chega 2x (reboot, re-sync)
            sig = assinatura(BRIEF_CURTO)
            if sig not in vistos:
                _guardar(h, digest_brief_text(BRIEF_CURTO))
                vistos.add(sig)
        resumos = [m for m in _fio(h) if m["engine"] == ENGINE_LAB_RESUMO]
        self.assertEqual(len(resumos), 1)

    def test_digest_vetado_pelo_modo_silencioso_nao_entra(self):
        self.assertIsNone(digest_relatorio(_RelatorioMudo()))

    def test_digest_respeita_teto_e_preserva_feito_e_decisao(self):
        turno = digest_brief_text(BRIEF_LONGO)
        linhas = turno[1].split("\n")
        self.assertLessEqual(len(linhas), MAX_LINHAS_FIO)
        texto = turno[1]
        self.assertIn("FEITO:", texto)
        self.assertIn("DECISÃO PEDIDA: aprovar o push", texto)

    def test_ponte_rejeita_lixo_nao_entra_no_fio(self):
        self.assertIsNone(outgoing_turn(None))
        self.assertIsNone(outgoing_turn({"text": "   "}))
        self.assertEqual(incoming_turns({"replies": "nao-e-lista"}), [])
        self.assertEqual(incoming_turns({}), [])


if __name__ == "__main__":
    unittest.main(verbosity=1)
