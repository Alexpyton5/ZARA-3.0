import sqlite3
from core.paths import user_data_dir, data_dir
print('user_data_dir:', user_data_dir())
print('data_dir:', data_dir())
# aprendizado
aprendizado_path = user_data_dir() / 'data' / 'aprendizado' / 'experiencias.db'
print('aprendizado db exists:', aprendizado_path.exists())
if aprendizado_path.exists():
    conn = sqlite3.connect(str(aprendizado_path))
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM episodios')
    epis = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM licoes')
    licoes = c.fetchone()[0]
    print(f'aprendizado: episodios={epis}, licoes={licoes}')
    if epis > 0:
        c.execute('SELECT pedido, acao, sucesso, reacao FROM episodios ORDER BY quando DESC LIMIT 5')
        rows = c.fetchall()
        print('ultimos 5 episodios:')
        for r in rows:
            print(r)
    conn.close()
# diario_auto
diario_path = data_dir() / 'diario_auto' / 'diario.db'
print('diario_auto db exists:', diario_path.exists())
if diario_path.exists():
    conn = sqlite3.connect(str(diario_path))
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM entradas')
    entradas = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM sugestoes')
    sugestoes = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM fechamentos')
    fechamentos = c.fetchone()[0]
    print(f'diario_auto: entradas={entradas}, sugestoes={sugestoes}, fechamentos={fechamentos}')
    if entradas > 0:
        c.execute('SELECT comando, acao, success, reacao_alex FROM entradas ORDER BY quando DESC LIMIT 5')
        rows = c.fetchall()
        print('ultimos 5 entradas:')
        for r in rows:
            print(r)
    conn.close()