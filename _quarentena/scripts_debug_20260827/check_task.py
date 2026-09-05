import sqlite3
conn = sqlite3.connect('C:/Users/alexp/AppData/Local/ZARA3/data/autonomy/zara_autonomy.db')
cur = conn.execute('SELECT * FROM tasks WHERE id="t_864d821a"')
row = cur.fetchone()
print('Columns:', [d[0] for d in cur.description])
if row:
    for i, v in enumerate(row):
        print(f'{i}: {v}')
else:
    print('Task t_864d821a not found')
conn.close()