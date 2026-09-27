import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import traceback, tempfile
from pathlib import Path
def run():
    logs=[]
    def log(m):
        logs.append(m)
        print(m)
    try:
        log('== ZARA RUNTIME VIVO - INICIO ==')
        from core.lab_v1.service import LabV1Service
        from core.lab_v1.store import LabStore
        tmpdir = Path(tempfile.mkdtemp(prefix='zara-runtime-prova-'))
        store = LabStore(tmpdir / 'lab.db')
        svc = LabV1Service()
        # force svc to use our tmp store for wiring test (monkey patch _store)
        svc._store = store
        adapter = svc._build_memory_adapter(store)
        log('1. adapter: ' + type(adapter).__name__)
        brain = None
        try:
            # _build already set _shared_brain
            brain = svc._shared_brain
            if brain is None:
                brain = svc.get_shared_brain()
            log('2. brain: ' + str(type(brain).__name__ if brain else 'None'))
        except Exception as e:
            log('2. brain erro: ' + str(e))
            traceback.print_exc()
        from core.lab_v1.runtime import LabRuntime
        try:
            from core.lab_v1.providers.registry import default_registry
            reg = default_registry()
        except:
            reg = None
        runtime = LabRuntime(store, reg, adapter)
        log('3. runtime ok')
        from core.lab_v1.domain import Session
        sess = Session(id='test_sess_1', team_id='test_team', objective='teste', acceptance_criteria=['c1'], state='OPEN')
        try:
            store.create_session(sess)
        except:
            pass
        ctx = runtime._session_context(sess, 'ola Zara')
        ctxr = runtime._session_context_with_recovery(sess, 'ola Zara')
        log('4. ctx len ' + str(len(ctx)) + ' rec ' + str(len(ctxr)) + ' diff ' + str(len(ctxr)-len(ctx)))
        log('   preserved ' + str(ctx in ctxr or ctx == ctxr))
        from core.ipc_handlers import IPCHandler
        import inspect
        log('5. IPCHandler sig ' + str(inspect.signature(IPCHandler.__init__)))
        src = Path('core/ipc_handlers.py').read_text(encoding='utf-8', errors='replace')
        log('6. get_second_brain existe ' + str('def get_second_brain' in src))
        h = object.__new__(IPCHandler)
        h._shared_brain = None
        h._shared_brain_failed = False
        h.lab_v1 = svc
        h.user_memory = None
        h.project_memory = None
        try:
            b2 = h.get_second_brain()
            log('7. IPC triangulo b2 ' + str(type(b2).__name__ if b2 else 'None') + ' reusa ' + str(b2 is brain))
        except Exception as e:
            log('7. IPC erro ' + str(e))
            traceback.print_exc()
        from memory.second_brain_composition import build_shared_second_brain
        log('8. composition import ok')
        log('== FIM ==')
        p = Path('D:/ZARA-LAB-WORK/prova-runtime-automated-20260916.txt')
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('\n'.join(logs), encoding='utf-8')
        log('prova gravada em ' + str(p))
        return 0
    except Exception as e:
        print('FATAL', e)
        traceback.print_exc()
        return 1
if __name__ == '__main__':
    sys.exit(run())
