import sys
sys.path.insert(0, 'C:/Users/alexp/Downloads/ZARA 3.0 CLEAN 002')
from core.paths import user_data_dir
import sqlite3
import time

aprendizado_db = user_data_dir() / "data" / "aprendizado" / "experiencias.db"

print("=== Recent episodios (last 10) ===")
try:
    conn = sqlite3.connect(str(aprendizado_db))
    cursor = conn.cursor()
    cursor.execute("""
        SELECT pedido, acao, sucesso, quando, reacao 
        FROM episodios 
        ORDER BY quando DESC 
        LIMIT 10
    """)
    rows = cursor.fetchall()
    for i, row in enumerate(rows):
        pedido, acao, sucesso, quando, reacao = row
        print(f"{i+1}. Pedido: '{pedido}'")
        print(f"   Acao: {acao}, Sucesso: {sucesso}")
        print(f"   Quando: {quando} ({time.ctime(quando)})")
        print(f"   Reacao: '{reacao}'")
        print()
    conn.close()
except Exception as e:
    print("Error:", e)

print("=== Checking for any reacoes != None and != '' ===")
try:
    conn = sqlite3.connect(str(aprendizado_db))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM episodios WHERE reacao IS NOT NULL AND reacao != ''")
    count = cursor.fetchone()[0]
    print(f"Episodios with non-empty reacao: {count}")
    if count > 0:
        cursor.execute("""
            SELECT pedido, acao, reacao 
            FROM episodios 
            WHERE reacao IS NOT NULL AND reacao != '' 
            ORDER BY quando DESC 
            LIMIT 5
        """)
        rows = cursor.fetchall()
        for row in rows:
            print(f"  Pedido: '{row[0]}', Acao: {row[1]}, Reacao: '{row[2]}'")
    conn.close()
except Exception as e:
    print("Error:", e)

print("\n=== Testing the actual phrases from recent episodios ===")
# Let's test some of the actual pedido values to see if they would trigger reactions
test_pedidos = [
    "minimize a janela",
    "coloque o volume em 30%",
    "deixa um pouco mais baixo",
    "deixa um pouco mais alto",
    "abrir o youtube",
    "fechar o youtube",
    "pausar o youtube",
    "continuar o youtube",
    "muda aba",
    "voltar aba"
]

from core.aprendizado import Aprendizado, _forma_do_pedido, _sem_acento
aprendizado = Aprendizado()

print("Testing forma do pedido for recent actions:")
for pedido in test_pedidos:
    forma = _forma_do_pedido(pedido)
    print(f"  '{pedido}' -> '{forma}'")

print("\nTesting if these formas would match learned lessons (if any existed):")
# Since we know licoes is empty, this will return None, but let's see the forma
for pedido in test_pedidos:
    forma = _forma_do_pedido(pedido)
    licao = aprendizado.licao_para(pedido)
    print(f"  '{pedido}' (forma: '{forma}') -> licao: {licao}")