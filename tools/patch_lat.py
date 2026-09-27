import pathlib 
p=pathlib.Path('core/ipc_handlers.py') 
t=p.read_text(encoding='utf-8') 
old=\\" system-metrics : self.handle_system_metrics,\"
