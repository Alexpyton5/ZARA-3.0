import sqlite3
from core.paths import user_data_dir, data_dir
print('=== aprendizizado licoes ===')
aprendizado_path = user_data_dir() / 'data' / 'aprendizado' / 'experiencias.db'
if aprendizado_path.exists():
    conn = sqlite3.connect(str(aprendizado_path))
    c = conn.cursor()
    c.execute('SELECT forma, acao, acertos, erros, ultima, exemplo FROM licoes')
    rows = c.fetchall()
    print(f'lições count: {len(rows)}')
    for r in rows:
        print(r)
    # check episodios with reacao
    c.execute('SELECT COUNT(*) FROM episodios WHERE reacao IS NOT NULL')
    reacao_count = c.fetchone()[0]
    print(f'episodios com reacao não nula: {reacao_count}')
    if reacao_count > 0:
        c.execute('SELECT pedido, acao, sucesso, reacao FROM episodios WHERE reacao IS NOT NULL ORDER BY quando DESC LIMIT 5')
        rows = c.fetchall()
        print('ultimos 5 episodios com reacao:')
        for r in rows:
            print(r)
    conn.close()
print('=== diario_auto detalhes ===')
diario_path = data_dir() / 'diario_auto' / 'diario.db'
if diario_path.exists():
    conn = sqlite3.connect(str(diario_path))
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM entradas')
    entradas = c.fetchone()[0]
    print(f'entradas: {entradas}')
    if entradas > 0:
        c.execute('SELECT comando, acao, success, reacao_alex FROM entradas ORDER BY quando DESC LIMIT 5')
        rows = c.fetchall()
        for r in rows:
            print(r)
    c.execute('SELECT COUNT(*) FROM sugestoes')
    sugestoes = c.fetchone()[0]
    print(f'sugestoes: {sugestoes}')
    c.execute('SELECT COUNT(*) FROM fechamentos')
    fechamentos = c.fetchone()[0]
    print(f'fechamentos: {fechamentos}')
    conn.close()