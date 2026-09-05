import sqlite3
from core.paths import user_data_dir

aprendizado_db = user_data_dir() / "data" / "aprendizado" / "experiencias.db"

print("Checking episodios for reacao...")
try:
    conn = sqlite3.connect(str(aprendizado_db))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM episodios WHERE reacao IS NOT NULL AND reacao != ''")
    reacao_count = cursor.fetchone()[0]
    print(f"Episodios with reacao: {reacao_count}")
    if reacao_count > 0:
        cursor.execute("SELECT pedido, acao, sucesso, reacao, quando FROM episodios WHERE reacao IS NOT NULL AND reacao != '' ORDER BY quando DESC LIMIT 5")
        rows = cursor.fetchall()
        for row in rows:
            print(f"  Pedido: {row[0]}, Acao: {row[1]}, Sucesso: {row[2]}, Reacao: {row[3]}, Quando: {row[4]}")
    else:
        print("No episodios with reacao found.")
    conn.close()
except Exception as e:
    print("Error:", e)