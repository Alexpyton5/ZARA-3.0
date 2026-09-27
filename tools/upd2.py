import pathlib 
p=pathlib.Path('.claude/TASK_BOARD.md') 
t=p.read_text(encoding='utf-8') 
t=t.replace('evidence: SOURCE/TEST 27/27 ok; batch 20 hang','evidence: SOURCE/TEST 27/27 ok 20260916 (16+11 fatia 5.26s+12.09s) + RUNTIME_AUTOMATED 20260916 wiring LAB+IPC SharedSecondBrain ok (prova-runtime-automated-20260916.txt) batch 20 hang') 
p.write_text(t,encoding='utf-8') 
print('updated2') 
