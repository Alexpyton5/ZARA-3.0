import pathlib 
p=pathlib.Path('core/ipc_handlers.py') 
t=p.read_text(encoding='utf-8') 
t=t.replace(chr(39)+'system-metrics'+chr(39)+': self.handle_system_metrics,',chr(39)+'system-metrics'+chr(39)+': self.handle_system_metrics,'+chr(10)+'            '+chr(39)+'latencia-resumo'+chr(39)+': self.handle_latencia_resumo,') 
print('step1 done', 'latencia-resumo' in t) 
old2='    async def handle_system_metrics(self, msg: IPCMessage):' 
new='    async def handle_latencia_resumo(self, msg: IPCMessage):'+chr(10)+'        try:'+chr(10)+'            from core.cronometro import relatorio'+chr(10)+'            dados = relatorio()'+chr(10)+'        except Exception as e:'+chr(10)+'            await self.send_response(msg.request_id, {'+chr(39)+'success'+chr(39)+': False, '+chr(39)+'error'+chr(39)+': str(e)})'+chr(10)+'            return'+chr(10)+'        await self.send_response(msg.request_id, {'+chr(39)+'success'+chr(39)+': True, '+chr(39)+'data'+chr(39)+': dados})'+chr(10)+chr(10)+'    async def handle_system_metrics(self, msg: IPCMessage):' 
t=t.replace(old2,new) 
p.write_text(t,encoding='utf-8') 
print('patched2', 'latencia-resumo' in t) 
