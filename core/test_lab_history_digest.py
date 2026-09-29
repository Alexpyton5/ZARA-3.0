"""Testes do resumo do Lab -> fio unificado (CONVERSA-UNICA).

Logica pura, sem rede, sem loop: os textos de boletim aqui tem o mesmo
formato que `lab_cycle_brief.boletim_de_ciclos()` e `lab_report.Relatorio`
produzem de verdade no app.
"""

import unittest

try:  # dentro do app (pacote core.*)
    from core.lab_history_digest import (
        ENGINE_LAB_RESUMO,
        MAX_LINHAS_FIO,
        assinatura,
        digest_brief_text,
        digest_relatorio,
    )
except ImportError:  # teste flat
    from lab_history_digest import (
        ENGINE_LAB_RESUMO,
        MAX_LINHAS_FIO,
        assinatura,
        digest_brief_text,
        digest_relatorio,
    )

try:  # para montar um Relatorio de verdade no teste
    from core.lab_report import BLOQUEIO, PROGRESSO, Relatorio
except ImportError:
    from lab_report import BLOQUEIO, PROGRESSO, Relatorio

BRIEF_PROGRESSO = """RELATÓRIO (PROGRESSO)
FEITO:
- ciclo(s) 1-3: 2 tarefa(s) concluída(s) de 2 despachada(s)
ESTADO:
- loop: RUNNING
- ciclos rodados: 3
SUGESTÃO:
- seguir o plano do turno"""

BRIEF_BLOQUEIO = """RELATÓRIO (BLOQUEIO)
FEITO:
- ciclo(s) 4-4: 0 tarefa(s) concluída(s) de 1 despachada(s)
ESTADO:
%s
ERRO:
- 1 tarefa(s) falharam e voltaram pra fila
DECISÃO PEDIDA: retomar o loop (resume) ou não"""


def brief_longo(n_estado=20):
    estado = "\n".join("- linha de estado %d" % i for i in range(n_estado))
    return BRIEF_BLOQUEIO % estado


class TestDigestBrief(unittest.TestCase):
    def test_engine_e_lab_resumo(self):
        self.assertEqual(ENGINE_LAB_RESUMO, "lab-resumo")

    def test_brief_progresso_vira_turno_assistant(self):
        turno = digest_brief_text(BRIEF_PROGRESSO)
        self.assertIsNotNone(turno)
        role, conteudo, engine = turno
        self.assertEqual(role, "assistant")
        self.assertEqual(engine, "lab-resumo")
        self.assertIn("FEITO:", conteudo)
        self.assertIn("2 tarefa(s) concluída(s)", conteudo)

    def test_brief_curto_nao_e_reescrito(self):
        turno = digest_brief_text(BRIEF_PROGRESSO)
        self.assertEqual(turno[1], BRIEF_PROGRESSO)

    def test_brief_longo_respeita_o_teto(self):
        turno = digest_brief_text(brief_longo())
        linhas = turno[1].split("\n")
        self.assertLessEqual(len(linhas), MAX_LINHAS_FIO)
        self.assertIn("FEITO:", turno[1])
        self.assertTrue(
            any("boletim completo" in ln for ln in linhas),
            "nota de corte honesta ausente",
        )

    def test_bloqueio_preserva_decisao_pedida(self):
        turno = digest_brief_text(brief_longo())
        self.assertIn("DECISÃO PEDIDA: retomar o loop (resume) ou não", turno[1])

    def test_texto_vazio_e_invalido_retorna_none(self):
        self.assertIsNone(digest_brief_text(""))
        self.assertIsNone(digest_brief_text("   "))
        self.assertIsNone(digest_brief_text(None))
        self.assertIsNone(digest_brief_text(123))
        self.assertIsNone(digest_brief_text([]))
        self.assertIsNone(digest_brief_text({"texto": "oi"}))

    def test_texto_opaco_ganha_origem_honesta(self):
        turno = digest_brief_text("o lab rodou 3 ciclos sem erro")
        self.assertIsNotNone(turno)
        self.assertTrue(turno[1].startswith("RESUMO DO LAB:"))
        self.assertIn("o lab rodou 3 ciclos sem erro", turno[1])

    def test_nada_e_inventado(self):
        entrada = set(brief_longo().split("\n"))
        turno = digest_brief_text(brief_longo())
        for ln in turno[1].split("\n"):
            if "boletim completo" in ln:
                continue
            self.assertIn(ln, entrada, "linha inventada no fio: %r" % ln)


class TestAssinatura(unittest.TestCase):
    def test_assinatura_estavel(self):
        self.assertEqual(assinatura(BRIEF_PROGRESSO), assinatura(BRIEF_PROGRESSO))

    def test_assinatura_muda_com_o_texto(self):
        self.assertNotEqual(assinatura(BRIEF_PROGRESSO), assinatura(brief_longo()))

    def test_fluxo_idempotente_do_chamador(self):
        # O fluxo documentado no modulo: o chamador guarda as assinaturas.
        vistos = set()
        texto = BRIEF_PROGRESSO
        sig = assinatura(texto)
        turnos = []
        for _ in range(2):  # o mesmo ciclo chega 2x
            if sig not in vistos:
                turno = digest_brief_text(texto)
                if turno:
                    turnos.append(turno)
                    vistos.add(sig)
        self.assertEqual(len(turnos), 1, "o mesmo ciclo virou 2 turnos")


class TestDigestRelatorio(unittest.TestCase):
    def test_relatorio_valido_vira_turno(self):
        rel = Relatorio(
            tipo=PROGRESSO,
            feito=["ciclo(s) 1-1: 1 tarefa(s) concluída(s) de 1 despachada(s)"],
            estado=["loop: RUNNING"],
        )
        turno = digest_relatorio(rel)
        self.assertIsNotNone(turno)
        self.assertEqual(turno[0], "assistant")
        self.assertEqual(turno[2], "lab-resumo")
        self.assertIn("FEITO:", turno[1])
        self.assertIn("RELATÓRIO (PROGRESSO)", turno[1])

    def test_relatorio_que_nao_passa_no_portao_nao_entra(self):
        # BLOQUEIO sem decisao pedida = vetado pelo modo silencioso.
        rel = Relatorio(tipo=BLOQUEIO, feito=["tentou"], estado=["travou"])
        self.assertFalse(rel.pode_falar())
        self.assertIsNone(digest_relatorio(rel))

    def test_progresso_sem_feito_nao_entra(self):
        rel = Relatorio(tipo=PROGRESSO, estado=["loop: RUNNING"])
        self.assertIsNone(digest_relatorio(rel))

    def test_lixo_nao_vira_turno(self):
        self.assertIsNone(digest_relatorio(None))
        self.assertIsNone(digest_relatorio({"tipo": PROGRESSO}))
        self.assertIsNone(digest_relatorio(object()))


if __name__ == "__main__":
    unittest.main()
