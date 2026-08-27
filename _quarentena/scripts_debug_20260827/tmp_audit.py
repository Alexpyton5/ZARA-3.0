import sqlite3
from core.paths import user_data_dir, data_dir

aprendizado_db = user_data_dir() / "data" / "aprendizado" / "experiencias.db"
diario_db = data_dir() / "diario_auto" / "diario.db"

print("=== Aprendizado DB ===")
try:
    conn = sqlite3.connect(str(aprendizado_db))
    cursor = conn.cursor()
    # Check licoes table
    cursor.execute("SELECT COUNT(*) FROM licoes")
    licoes_count = cursor.fetchone()[0]
    print(f"Licoes count: {licoes_count}")
    if licoes_count > 0:
        cursor.execute("SELECT forma, acao, acertos, erros, exemplo FROM licoes ORDER BY (erros + acertos) DESC LIMIT 10")
        rows = cursor.fetchall()
        for row in rows:
            print(f"  Forma: {row[0]}, Acao: {row[1]}, Acertos: {row[2]}, Erros: {row[3]}, Exemplo: {row[4]}")
    conn.close()
except Exception as e:
    print("Error aprendizado:", e)

print("\n=== Diario Auto DB ===")
try:
    conn = sqlite3.connect(str(diario_db))
    cursor = conn.cursor()
    # Check entradas
    cursor.execute("SELECT COUNT(*) FROM entradas")
    entradas_count = cursor.fetchone()[0]
    print(f"Entradas count: {entradas_count}")
    # Check sugestoes
    cursor.execute("SELECT COUNT(*) FROM sugestoes")
    sugestoes_count = cursor.fetchone()[0]
    print(f"Sugestoes count: {sugestoes_count}")
    if sugestoes_count > 0:
        cursor.execute("SELECT dia, regra, chave_agregacao, total_ocorrencias, sucessos, falhas, status FROM sugestoes ORDER BY dia DESC LIMIT 10")
        rows = cursor.fetchall()
        for row in rows:
            print(f"  Dia: {row[0]}, Regra: {row[1]}, Chave: {row[2]}, Total: {row[3]}, Sucessos: {row[4]}, Falhas: {row[5]}, Status: {row[6]}")
    # Check fechamentos
    cursor.execute("SELECT COUNT(*) FROM fechamentos")
    fechamentos_count = cursor.fetchone()[0]
    print(f"Fechamentos count: {fechamentos_count}")
    if fechamentos_count > 0:
        cursor.execute("SELECT dia, total_entradas_unicas, total_ocorrencias, sucessos, falhas, taxa_sucesso FROM fechamentos ORDER BY dia DESC LIMIT 5")
        rows = cursor.fetchall()
        for row in rows:
            print(f"  Dia: {row[0]}, Unicas: {row[1]}, Ocorrencias: {row[2]}, Sucessos: {row[3]}, Falhas: {row[4]}, Taxa: {row[5]}")
    conn.close()
except Exception as e:
    print("Error diario:", e)

print("\n=== Checking for duplication between systems ===")
# We can't directly compare, but we can note that both systems store similar data.
# Aprendizado stores episodios and licoes (learned lessons).
# DiarioAuto stores entradas (raw entries) and sugestoes (suggestions).
# The aprendizado system is used for learning from reactions (aprovou/corrigiu).
# The diario_auto system is used for generating suggestions for review.
# They are complementary, but we should check if there is any overlap in function that might cause duplication.

print("\n=== Checking initiative engine for proatividade ===")
# Look for files that use the learned data to make proactive suggestions.
# We already saw in the audit report (proatividade_memoria_audit.md) that there is a note:
#   - Substituir o conselho estático em `InitiativeEngine._get_advice` por um gerador baseado em padrões aprendidos
#     (ex: usando dados do `DiarioAuto` ou `Aprendizado`).
# Let's check the InitiativeEngine.

import os
initiative_engine_path = os.path.join("core", "initiative.py")
if os.path.exists(initiative_engine_path):
    print(f"Initiative engine found at: {initiative_engine_path}")
    # We can read the file to see if it uses aprendizado or diario_auto.
    with open(initiative_engine_path, "r", encoding="utf-8") as f:
        content = f.read()
        if "aprendizado" in content.lower():
            print("  -> Uses aprendizado")
        if "diario" in content.lower():
            print("  -> Uses diario_auto")
else:
    print("Initiative engine not found at core/initiative.py")

print("\n=== End of audit ===")