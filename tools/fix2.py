import pathlib 
p=pathlib.Path('tools/prova_runtime_vivo.py') 
t=p.read_text(encoding='utf-8') 
old=pathlib.Path('old.txt').read_text(encoding='utf-8').strip() 
new=pathlib.Path('new.txt').read_text(encoding='utf-8').strip() 
t=t.replace(old,new) 
t=t.replace('from core.lab_v1.domain import Session, new_id','from core.lab_v1.domain import Session') 
p.write_text(t,encoding='utf-8') 
print('patched') 
