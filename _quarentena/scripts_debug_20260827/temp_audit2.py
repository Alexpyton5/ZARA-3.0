import sqlite3
from core.paths import user_data_dir, data_dir
print('=== aprendizizado licoes (detailed) ===')
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
    # check total episodios
    c.execute('SELECT COUNT(*) FROM episodios')
    total_episodios = c.fetchone()[0]
    print(f'total episodios: {total_episodios}')
    conn.close()
print('=== diario_auto detalhes (detailed) ===')
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
    # check if there are any suggestions that are pending
    c.execute('SELECT id, dia, regra, chave_agregacao, comando_representativo, acao, total_ocorrencias, sucessos, falhas, sugestoes_json, review_required, auto_apply, status FROM sugestoes WHERE status = \"pendente\"')
    pendentes = c.fetchall()
    print(f'sugestoes pendentes: {len(pendentes)}')
    for p in pendentes[:3]:
        print(p)
    conn.close()
print('=== iniciativa engine config ===')
from core.initiative.config import default_config
print(f'config: enabled={default_config.enabled}, check_interval_seconds={default_config.check_interval_seconds}, utility_threshold={default_config.utility_threshold}, max_interruptions_per_hour={default_config.max_interruptions_per_hour}, silent_start_hour={default_config.silent_start_hour}, silent_end_hour={default_config.silent_end_hour}, history_size={default_config.history_size}')
print('=== iniciativa engine engine.py placeholders ===')
# We already know from the source that _get_utility returns 0.5 and _get_advice returns static string.
# Let's just note that.
print('InitiativeEngine._get_utility returns 0.5 (hardcoded)')
print('InitiativeEngine._get_advice returns \"Lembrete: basta um pequeno passo para começar.\" (hardcoded)')
print('=== checking if initiative engine is started in orchestrator ===')
# We can look at the orchestrator code to see if it starts the initiative engine.
import os
orchestrator_path = os.path.join(os.path.dirname(__file__), 'core', 'zara_orchestrator.py')
if os.path.exists(orchestrator_path):
    with open(orchestrator_path, 'r', encoding='utf-8') as f:
        content = f.read()
        # Look for InitiativeEngine
        if 'InitiativeEngine' in content:
            print('InitiativeEngine found in zara_orchestrator.py')
            # Check if it's started
            if '.start()' in content or 'start()' in content:
                print('Found start() call for InitiativeEngine')
            else:
                print('No start() call found for InitiativeEngine in zara_orchestrator.py')
        else:
            print('InitiativeEngine NOT found in zara_orchestrator.py')
else:
    print('zara_orchestrator.py not found')
print('=== checking memoria_automatica for any obvious issues ===')
# We can check if the memoria_automatica module is being used anywhere.
# Let's just check the imports in ipc_handlers.py for memoria_automatica.
ipc_handlers_path = os.path.join(os.path.dirname(__file__), 'core', 'ipc_handlers.py')
if os.path.exists(ipc_handlers_path):
    with open(ipc_handlers_path, 'r', encoding='utf-8') as f:
        content = f.read()
        if 'memoria_automatica' in content:
            print('memoria_automatica found in ipc_handlers.py')
        else:
            print('memoria_automatica NOT found in ipc_handlers.py')
else:
    print('ipc_handlers.py not found')