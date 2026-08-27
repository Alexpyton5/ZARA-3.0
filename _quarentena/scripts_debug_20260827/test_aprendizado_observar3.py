import sys
sys.path.insert(0, 'C:/Users/alexp/Downloads/ZARA 3.0 CLEAN 002')
from core.aprendizado import Aprendizado

aprendizado = Aprendizado()

# First, register an action so that self._ultimo is set
pedido = "minimize a janela"
acao = "window_minimize"
sucesso = True
resultado = "janela minimizada"
origem = "test"

# Register the action
rid = aprendizado.registrar_acao(pedido, acao, sucesso, resultado, origem)
print(f"Registered action with id: {rid}")
print(f"  pedido: {pedido}")
print(f"  acao: {acao}")
print(f"  sucesso: {sucesso}")
print(f"  resultado: {resultado}")
print(f"  origem: {origem}")
print()

# Now test the observar_reacao method with some sample phrases
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

print("Testing observar_reacao (after registering an action):")
for phrase in test_phrases:
    result = aprendizado.observar_reacao(phrase)
    print(f"  '{phrase}' -> {result}")

# Also test that after a reaction, the _ultimo is cleared (so next reaction without new action returns None)
print("\nTesting that _ultimo is cleared after reaction:")
print(f"  Before second reaction: _ultimo is {aprendizado._ultimo is not None}")
veredito = aprendizado.observar_reacao("não é isso")
print(f"  Second reaction 'não é isso' -> {veredito}")
print(f"  After second reaction: _ultimo is {aprendizado._ultimo is not None}")