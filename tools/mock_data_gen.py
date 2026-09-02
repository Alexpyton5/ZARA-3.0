"""ZARA-MOCK-DATA-GEN-001 (Alex, 2026-08-28)

Peca isolada. Gera dado fake em JSON pra apoiar teste de desenvolvimento.
Zero dependencia nova (so `random`/`uuid`/biblioteca padrao) -- nao usa
Faker de proposito, pra nao adicionar pacote so pra isso.
"""
from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta

_FIRST_NAMES = ("Ana", "Bruno", "Carla", "Diego", "Elisa", "Felipe", "Gabriela", "Heitor", "Ivana", "João")
_LAST_NAMES = ("Silva", "Souza", "Oliveira", "Costa", "Pereira", "Almeida", "Nunes", "Ramos", "Teixeira", "Barbosa")
_PRODUCT_NAMES = ("Teclado Mecânico", "Monitor 27\"", "Mouse Sem Fio", "Headset Gamer", "Webcam HD", "SSD 1TB", "Cadeira Gamer", "Notebook", "Roteador Wi-Fi", "Carregador USB-C")
_LOG_LEVELS = ("INFO", "WARNING", "ERROR", "DEBUG")
_LOG_MESSAGES = ("Conexão estabelecida", "Timeout na requisição", "Usuário autenticado", "Falha ao salvar arquivo", "Cache invalidado", "Processo iniciado", "Processo finalizado")

_SUPPORTED_TYPES = ("users", "products", "logs")


def _mock_user(_index: int) -> dict:
    first = random.choice(_FIRST_NAMES)
    last = random.choice(_LAST_NAMES)
    return {
        "id": str(uuid.uuid4()),
        "name": f"{first} {last}",
        "email": f"{first.lower()}.{last.lower()}@example.com",
        "age": random.randint(18, 70),
    }


def _mock_product(_index: int) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "name": random.choice(_PRODUCT_NAMES),
        "price": round(random.uniform(29.9, 4999.9), 2),
        "stock": random.randint(0, 500),
    }


def _mock_log(_index: int) -> dict:
    timestamp = datetime.now() - timedelta(minutes=random.randint(0, 10_000))
    return {
        "id": str(uuid.uuid4()),
        "level": random.choice(_LOG_LEVELS),
        "message": random.choice(_LOG_MESSAGES),
        "timestamp": timestamp.isoformat(),
    }


_GENERATORS = {
    "users": _mock_user,
    "products": _mock_product,
    "logs": _mock_log,
}


def generate_mock_json(data_type: str, count: int = 10) -> list[dict]:
    """Gera `count` registros fake do tipo pedido. Tipos suportados:
    'users', 'products', 'logs' -- lista fechada de propósito, pra não
    devolver um formato inventado que ninguém pediu."""
    key = str(data_type or "").strip().lower()
    generator = _GENERATORS.get(key)
    if generator is None:
        raise ValueError(
            f"Tipo '{data_type}' não suportado. Use um de: {', '.join(_SUPPORTED_TYPES)}."
        )
    if count < 1:
        raise ValueError("count precisa ser pelo menos 1.")
    return [generator(i) for i in range(count)]
