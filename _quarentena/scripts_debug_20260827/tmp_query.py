import sqlite3
from core.paths import user_data_dir, data_dir

aprendizado_db = user_data_dir() / "data" / "aprendizado" / "experiencias.db"
diario_db = data_dir() / "diario_auto" / "diario.db"

print("Aprendizado DB:", aprendizado_db)
print("Diario DB:", diario_db)

try:
    conn = sqlite3.connect(str(aprendizado_db))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM episodios")
    count = cursor.fetchone()[0]
    print("Episodios count:", count)
    if count > 0:
        cursor.execute("SELECT pedido, acao, sucesso, quando FROM episodios ORDER BY quando DESC LIMIT 5")
        rows = cursor.fetchall()
        for row in rows:
            print("  Pedido:", row[0], "Acao:", row[1], "Sucesso:", row[2], "Quando:", row[3])
    conn.close()
except Exception as e:
    print("Error aprendizado:", e)

try:
    conn = sqlite3.connect(str(diario_db))
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM entradas")
    count = cursor.fetchone()[0]
    print("Entradas count:", count)
    if count > 0:
        cursor.execute("SELECT comando, acao, success, quando FROM entradas ORDER BY quando DESC LIMIT 5")
        rows = cursor.fetchall()
        for row in rows:
            print("  Comando:", row[0], "Acao:", row[1], "Success:", row[2], "Quando:", row[3])
    conn.close()
except Exception as e:
    print("Error diario:", e)