import sys
sys.path.insert(0, 'C:/Users/alexp/Downloads/ZARA 3.0 CLEAN 002')
from core.aprendizado import Aprendizado, _forma_do_pedido, _sem_acento

# Create an instance (it will create the DB if not exists, but we already have one)
aprendizado = Aprendizado()

# Test the observar_reacao method with some sample phrases
test_phrases = [
    "não é isso que eu pedi",
    "isso mesmo",
    "não funcionou",
    "deu certo",
    "me conta uma piada",
    "não é isso",
    "certeza",
    "errado",
    "acertou",
    "não tá certo",
    "tá errado",
    "tá certo",
    "não é essa",
    "é isso mesmo",
    "não foi isso",
    "foi isso mesmo",
    "não é isso aí",
    "isso aí está certo",
    "não tá bom",
    "tá bom"
]

print("Testing observar_reacao:")
for phrase in test_phrases:
    result = aprendizado.observar_reacao(phrase)
    print(f"  '{phrase}' -> {result}")

# Also test the _forma_do_pedido function
print("\nTesting _forma_do_pedido:")
test_pedidos = [
    "minimize a janela",
    "minimiza essa janela aí",
    "abaixa o volume",
    "diminui o volume",
    "coloca o volume em 30%",
    "coloca o volume em trente por cento",
    "abre o youtube",
    "abrir o youtube",
    "abriu o youtube"
]
for pedido in test_pedidos:
    forma = _forma_do_pedido(pedido)
    print(f"  '{pedido}' -> '{forma}'")