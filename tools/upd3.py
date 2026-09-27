import pathlib 
p=pathlib.Path('.claude/TASK_BOARD.md') 
t=p.read_text(encoding='utf-8') 
t=t.replace('files: core/cronometro.py, core/ipc_handlers.py\n  DoD: mediana <800ms medida com [VOICE_TRACE]','files: core/cronometro.py, core/ipc_handlers.py\n  DoD: mediana <800ms medida com [VOICE_TRACE]'+chr(10)+'  evidence: 20260916 mediana 16688ms (18 turnos, 182 descartados) medida real via relatorio(), IPC latencia-resumo implementado e testado (handler ok), segunda-viagem 6311ms identificada como gargalo P10') 
p.write_text(t,encoding='utf-8') 
print('upd3 done') 
