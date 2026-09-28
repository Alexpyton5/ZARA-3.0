"""
Testes das primeiras propostas do backlog (Fase D "LAB VIVO").

Prova, contra o lab_backlog.py REAL: as 8 propostas entram PROPOSTO, com
motivo+risco+origem, idempotência de verdade (re-seed não duplica, nem depois
de aprovação), e a ordem de prioridade é determinística.
"""

import unittest

try:  # dentro do app (pacote core.*)
    from core.lab_backlog import BacklogError, BacklogState, LabBacklog
    from core.lab_seed_proposals import SEED_PROPOSALS, seed, seed_marker, seeded_keys
except ImportError:  # teste flat
    from lab_backlog import BacklogError, BacklogState, LabBacklog
    from lab_seed_proposals import SEED_PROPOSALS, seed, seed_marker, seeded_keys


def _backlog():
    return LabBacklog(clock=lambda: "2026-09-28T02:35:00-03:00")


class TestSeedProposals(unittest.TestCase):
    def test_seed_registra_8_itens_propostos(self):
        bl = _backlog()
        created = seed(bl)
        self.assertEqual(len(created), 8)
        self.assertEqual(created, [f"BLG-{i:04d}" for i in range(1, 9)])
        for item_id in created:
            self.assertEqual(bl.get(item_id).state, BacklogState.PROPOSED)

    def test_seed_idempotente(self):
        bl = _backlog()
        first = seed(bl)
        second = seed(bl)
        self.assertEqual(second, [])
        keys = seeded_keys(bl)
        self.assertEqual(len(keys), 8)
        for slug, item_id in keys.items():
            self.assertIn(item_id, first)
            self.assertIn(seed_marker(slug), bl.get(item_id).description)

    def test_seed_nao_duplica_apos_aprovacao(self):
        bl = _backlog()
        seed(bl)
        bl.approve("BLG-0001", by="CEO")
        self.assertEqual(seed(bl), [])
        self.assertEqual(len(bl.ranked()), 8)

    def test_descricoes_tem_motivo_risco_origem(self):
        for p in SEED_PROPOSALS:
            desc = str(p["description"])
            for parte in ("Motivo:", "Risco:", "Origem:"):
                self.assertIn(parte, desc, f"item {p['slug']} sem {parte}")

    def test_limites_de_texto(self):
        for p in SEED_PROPOSALS:
            self.assertLessEqual(len(str(p["title"])), 140, p["slug"])
            full = f"{p['description']} {seed_marker(str(p['slug']))}"
            self.assertLessEqual(len(full), 1000, p["slug"])

    def test_scores_corretos(self):
        bl = _backlog()
        seed(bl)
        # fórmula: impacto*3 + urgência*2 - custo*2
        self.assertEqual(bl.get("BLG-0001").score, 5 * 3 + 4 * 2 - 4 * 2)  # 15
        self.assertEqual(bl.get("BLG-0003").score, 3 * 3 + 3 * 2 - 1 * 2)  # 13

    def test_plan_for_ceo_ordena_por_score(self):
        bl = _backlog()
        seed(bl)
        plan = bl.plan_for_ceo()
        scores = [i.score for i in plan]
        self.assertEqual(scores, sorted(scores, reverse=True))
        self.assertEqual(plan[0].item_id, "BLG-0001")  # suite-42-falhas, score 15
        self.assertEqual(plan[-1].score, 6)

    def test_slugs_unicos(self):
        slugs = [str(p["slug"]) for p in SEED_PROPOSALS]
        self.assertEqual(len(slugs), len(set(slugs)))

    def test_ceo_aprova_item_semeado(self):
        bl = _backlog()
        seed(bl)
        item = bl.approve("BLG-0002", by="CEO")
        self.assertEqual(item.state, BacklogState.APPROVED)
        with self.assertRaises(BacklogError):
            bl.approve("BLG-0003", by="ENGINEER")

    def test_seed_parcial_nao_colide(self):
        bl = _backlog()
        outro = bl.propose("Item do Lab", "proposta normal do Lab", "ENGINEER", 3, 3, 3)
        self.assertEqual(outro.item_id, "BLG-0001")
        created = seed(bl)
        self.assertEqual(len(created), 8)
        self.assertEqual(created[0], "BLG-0002")
        self.assertEqual(len(bl.ranked()), 9)


if __name__ == "__main__":
    unittest.main()
