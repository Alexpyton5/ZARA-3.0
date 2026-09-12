"""Renderer interaction contracts with fake IPC; never opens apps or hardware.

Screenshots for visual acceptance come from the real Electron runtime, not this fixture.
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = """
window.calls=[];window.events={};window.historyFixture=[];window.voiceMode='error';window.voiceTransport='renderer';
const ok=(name,result={success:true})=>(...args)=>{window.calls.push([name,...args]);return Promise.resolve(result)};
window.zaraIPC={
 desktop:{openApp:ok('app'),openExternal:ok('external'),openSettings:ok('settings'),openFolder:ok('folder')},
 engine:{list:ok('engines',{engines:[{id:'auto_fast',name:'Automático'}]}),change:ok('engine')},
 config:{get:ok('config',{current_engine:'auto_fast'})},
 system:{metrics:ok('metrics',{cpu:31,ram:42,disk:67}),info:ok('info',{os:'Windows'})},
 projectMemory:{context:ok('projects',{success:true,active_project_id:null,projects:[],legacy_document_keys:[]}),get:ok('doc')},
 memoryGalaxy:{list:ok('memories',{success:true,nodes:[]})},userMemory:{add:ok('remember')},
 reminders:{list:ok('reminders',{success:true,reminders:[]}),create:ok('reminder-create')},
 lab:{state:ok('lab',{tasks:[],proposals:[],workers:[{id:'zara',name:'ZARA',can_chat:true}],messages:[{id:'m1',author:'zara',target:'alex',content:'Contexto registrado de teste',created_at:1}],activity:[]}),send:ok('lab-send',{success:true,state:'QUEUED'})},
 action:{execute:async(name,params)=>{window.calls.push(['action',name,params]);return name==='os_power_plan_set'?{success:false,error:'TEST_POWER_DENIED'}:{success:true,result:{success:true,data:name==='os_power_plan_list'?[{guid:'8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c',name:'Alto desempenho',active:false}]:[]}}}},
 conversationHistory:{list:async()=>({messages:window.historyFixture})},
 message:{send:async payload=>{window.calls.push(['send',payload]);window.historyFixture.push({role:'user',content:payload.message,timestamp:1},{role:'assistant',content:'Resposta de teste',timestamp:2});return {response:'Resposta de teste'}},interrupt:ok('interrupt')},
 voice:{start:async()=>{window.calls.push(['voice-start']);return window.voiceMode==='error'?{success:false,error:'Serviço de voz indisponível'}:{success:true,mode:window.voiceMode,audio_transport:window.voiceTransport}},stop:ok('voice-stop'),mute:ok('mute'),status:ok('voice-status'),sendMicChunk:()=>{}},
 window:{minimize:ok('minimize'),maximize:ok('maximize'),close:ok('close')},
 on:new Proxy({}, {get:(_,name)=>callback=>{window.events[name]=callback;return()=>{delete window.events[name]}}})
};
"""

def main():
    checks = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width":1671,"height":941})
        page.add_init_script(FIXTURE)
        errors=[]
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto('http://localhost:5173/', wait_until='networkidle')
        for name in ['Conversas','Projetos','Arquivos','Aplicativos','Automações','Memórias','ZARA Lab','Dispositivos','Sistema','Configurações']:
            page.locator('.zh-nav').get_by_role('button',name=name,exact=True).click()
            expect(page.get_by_role('dialog',name=name,exact=True)).to_be_visible()
            page.get_by_role('button',name='Fechar painel',exact=True).click()
        checks.append('10 sidebar destinations')
        for name in ['Aplicativos','Arquivos','Ajuda','Histórico','Mais opções']:
            page.locator('.zh-dock').get_by_role('button',name=name,exact=True).click()
            expect(page.get_by_role('dialog',name=name,exact=True)).to_be_visible()
            page.keyboard.press('Escape')
            expect(page.get_by_role('dialog')).to_have_count(0)
        checks.append('5 dock destinations and Escape/focus')
        page.get_by_role('button',name='Abrir ZARA Lab',exact=True).click()
        expect(page.get_by_text('Contexto registrado de teste',exact=True)).to_be_visible()
        page.get_by_label('Conversar com',exact=True).select_option('zara')
        page.get_by_label('O que vamos fazer?',exact=True).fill('Objetivo de teste')
        page.get_by_role('button',name='Enviar ao participante',exact=True).click()
        expect(page.get_by_text('Mensagem recebida pelo Lab. A resposta aparecerá na conversa.',exact=True)).to_be_visible()
        assert [call[1] for call in page.evaluate('window.calls') if call[0]=='lab-send']==[{'author':'alex','target':'zara','content':'Objetivo de teste'}]
        page.keyboard.press('Escape')
        checks.append('Lab opens saved conversation; explicit send reports acknowledgement')
        page.locator('.zh-nav').get_by_role('button',name='Aplicativos',exact=True).click()
        for name in ['VS Code','Figma','Postman','Docker']:
            page.get_by_role('button',name='Abrir '+name,exact=True).click()
            page.wait_for_function('window.calls.filter(c=>c[0]==="app").length >= '+str(['VS Code','Figma','Postman','Docker'].index(name)+1))
        page.keyboard.press('Escape')
        for name in ['WhatsApp','Telegram','Instagram','Gmail']:
            page.get_by_role('button',name='Abrir '+name,exact=True).click()
            page.wait_for_timeout(20)
        assert [call[1] for call in page.evaluate('window.calls') if call[0]=='app']==['vscode','figma','postman','docker']
        assert [call[1] for call in page.evaluate('window.calls') if call[0]=='external']==['whatsapp','telegram','instagram','gmail']
        checks.append('4 app and 4 service dispatch contracts')
        page.get_by_role('textbox',name='Como posso ajudar?',exact=True).fill('Teste de texto')
        page.get_by_role('button',name='Enviar mensagem',exact=True).click()
        expect(page.get_by_role('dialog',name='Conversas')).to_be_visible()
        expect(page.get_by_text('Resposta de teste',exact=True)).to_be_visible()
        page.get_by_role('button',name='Fechar painel').click()
        page.get_by_role('textbox',name='Como posso ajudar?',exact=True).fill('Segundo turno')
        page.get_by_role('button',name='Enviar mensagem',exact=True).click()
        expect(page.get_by_role('dialog',name='Conversas')).to_be_visible()
        sends=[call[1] for call in page.evaluate('window.calls') if call[0]=='send']
        assert sends[-1]['engine']=='auto_fast' and len(sends[-1]['history'])==2
        page.get_by_role('button',name='Fechar painel').click()
        checks.append('text response, selected engine and second-turn context')
        page.get_by_role('button',name='Abrir modo voz',exact=True).click()
        expect(page.get_by_text('Serviço de voz indisponível',exact=True)).to_be_visible()
        expect(page.get_by_role('button',name='Abrir modo voz')).to_have_attribute('aria-pressed','false')
        page.evaluate("window.voiceMode='local'")
        page.get_by_role('button',name='Abrir modo voz',exact=True).click()
        expect(page.get_by_role('button',name='Parar modo voz',exact=True)).to_have_attribute('aria-pressed','true')
        page.get_by_role('button',name='Parar modo voz',exact=True).click()
        expect(page.get_by_role('button',name='Abrir modo voz')).to_have_attribute('aria-pressed','false')
        assert any(call[0]=='voice-stop' for call in page.evaluate('window.calls'))
        checks.append('voice failure is visible; local start/stop ownership')
        page.evaluate("()=>{window.voiceMode='gemini_live'; navigator.mediaDevices.getUserMedia=async()=>{throw new Error('TEST_PERMISSION_DENIED')}}")
        page.get_by_role('button',name='Abrir modo voz',exact=True).click()
        expect(page.get_by_text('Microfone indisponível. Verifique o dispositivo e a permissão de áudio.',exact=True)).to_be_visible()
        assert len([call for call in page.evaluate('window.calls') if call[0]=='voice-stop'])>=2
        checks.append('renderer microphone denial stops backend session')
        page.evaluate("window.voiceTransport='local'")
        page.get_by_role('button',name='Abrir modo voz',exact=True).click()
        expect(page.get_by_role('button',name='Parar modo voz',exact=True)).to_have_attribute('aria-pressed','true')
        page.get_by_role('button',name='Parar modo voz',exact=True).click()
        checks.append('Gemini local transport does not open a second microphone')
        page.get_by_role('button',name='Performance',exact=False).click()
        expect(page.get_by_text('TEST_POWER_DENIED',exact=True)).to_be_visible()
        checks.append('power plan rejection is visible and does not claim success')
        page.get_by_role('button',name='Analisar agora',exact=True).click()
        expect(page.get_by_text('CPU, memória e disco sem uso elevado nesta leitura.',exact=True)).to_be_visible()
        checks.append('diagnostic uses measured resources')
        assert not errors, errors
        browser.close()
    result={'status':'passed','checks':checks,'fixture':'fake IPC, no physical actions'}
    (ROOT/'artifacts/visual-qa/renderer-contracts.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))

if __name__=='__main__':main()
