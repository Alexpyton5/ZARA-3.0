"""Testes da ponte Conselheira -> historico unificado (CONVERSA-UNICA).

Logica pura, sem rede, sem Gmail, sem modelo: os payloads aqui tem o
mesmo formato que `ZoeChatRelay.send_message()` e `ZoeChatRelay.sync()`
devolvem de verdade.
"""

import unittest

try:  # dentro do app (pacote core.*)
    from core.conselheira_history_bridge import (
        ENGINE_PONTE_ZOE,
        incoming_turns,
        outgoing_turn,
    )
except ImportError:  # teste flat
    from conselheira_history_bridge import (
        ENGINE_PONTE_ZOE,
        incoming_turns,
        outgoing_turn,
    )


class TestOutgoingTurn(unittest.TestCase):
    def test_send_valido_vira_turno_user(self):
        p = {"chat_id": "CHAT-123", "text": "oi zoe, tudo bem?", "created_at": 1.0}
        self.assertEqual(outgoing_turn(p), ("user", "oi zoe, tudo bem?", "ponte-zoe"))

    def test_engine_e_ponte_zoe(self):
        self.assertEqual(ENGINE_PONTE_ZOE, "ponte-zoe")

    def test_send_sem_texto_retorna_none(self):
        self.assertIsNone(outgoing_turn({"chat_id": "CHAT-1"}))

    def test_send_texto_vazio_retorna_none(self):
        self.assertIsNone(outgoing_turn({"text": "   "}))

    def test_send_nao_dict_retorna_none(self):
        self.assertIsNone(outgoing_turn(None))
        self.assertIsNone(outgoing_turn([]))

    def test_send_apara_espacos(self):
        self.assertEqual(
            outgoing_turn({"text": "  com espacos  "}),
            ("user", "com espacos", "ponte-zoe"),
        )


class TestIncomingTurns(unittest.TestCase):
    def test_duas_respostas_viram_dois_turnos(self):
        r = {
            "sent": ["CHAT-1"],
            "replies": [
                {"chat_id": "CHAT-1", "reply": "tudo certo por aqui",
                 "received_at": 2.0, "matched": True},
                {"chat_id": "CHAT-2", "reply": "segunda resposta",
                 "received_at": 3.0, "matched": False},
            ],
            "last_sync_at": 4.0,
        }
        turns = incoming_turns(r)
        self.assertEqual(len(turns), 2)
        self.assertEqual(turns[0], ("assistant", "tudo certo por aqui", "ponte-zoe"))
        self.assertEqual(turns[1][0], "assistant")
        self.assertEqual(turns[1][1], "segunda resposta")

    def test_sync_sem_respostas_retorna_lista_vazia(self):
        self.assertEqual(
            incoming_turns({"sent": [], "replies": [], "last_sync_at": 1.0}), [])

    def test_sync_sem_chave_replies_retorna_lista_vazia(self):
        self.assertEqual(incoming_turns({"sent": []}), [])

    def test_sync_nao_dict_retorna_lista_vazia(self):
        self.assertEqual(incoming_turns(None), [])

    def test_reply_vazio_e_pulado(self):
        self.assertEqual(
            incoming_turns({"replies": [{"reply": "  "}, {"reply": "ok"}]}),
            [("assistant", "ok", "ponte-zoe")],
        )

    def test_item_nao_dict_e_pulado(self):
        self.assertEqual(
            incoming_turns({"replies": ["lixo", {"reply": "ok"}]}),
            [("assistant", "ok", "ponte-zoe")],
        )

    def test_replies_nao_lista_retorna_lista_vazia(self):
        self.assertEqual(incoming_turns({"replies": "lixo"}), [])


if __name__ == "__main__":
    unittest.main()
