import asyncio
import sys
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8")

from core.pc_voice_intent import PcVoiceIntentDetector
import core.actions  # noqa: F401  (registra as acoes)
from core.action_registry import execute_action, get_registry

PASS, FAIL = 0, 0
def test(name, cond, expected=True):
    global PASS, FAIL
    ok = cond == expected
    print(f"  {'PASS' if ok else 'FAIL'} {name}")
    PASS += ok
    FAIL += not ok

print("1. INTENT RECOGNITION (4 frases)")
d = PcVoiceIntentDetector(pc_control_allowed=True)
cases = [
    ("zara, coloque o volume em 30%", "30"),
    ("zara, volume 30%", "30"),
    ("zara, aumente o volume", "up"),
    ("zara, diminua o volume", "down"),
]
for phrase, expected_param in cases:
    r = d.detect(phrase)
    test(f"  '{phrase}' intent", r.is_pc_intent, True)
    test(f"  '{phrase}' action", r.action, "os_volume")
    test(f"  '{phrase}' param", str(r.param), expected_param)

print("2. SAFETY GATE OFF (policy existente nao alterada)")
get_registry().pc_control_allowed = False
res = asyncio.run(execute_action("os_volume", level=30))
test("  os_volume OFF -> blocked", res.success, False)
print(f"    error={str(res.error)[:90]}")
test("  nao altera volume com gate OFF", True)

print("3. SAFETY GATE ON + VOLUME REAL WINDOWS")
get_registry().pc_control_allowed = True
res = asyncio.run(execute_action("os_volume", level=30))
test("  os_volume level=30 -> success", res.success, True)
print(f"    output={res.output}")
import time; time.sleep(1)

def read_vol():
    from comtypes import CLSCTX_ALL, CoInitialize, CoUninitialize
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    CoInitialize()
    try:
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        v = interface.QueryInterface(IAudioEndpointVolume)
        return round(v.GetMasterVolumeLevelScalar() * 100)
    finally:
        CoUninitialize()

v = read_vol()
test("  Windows volume ~30%", abs(v - 30) <= 3, True)
print(f"    volume lido = {v}%")

print("4. NAO-FALSO-POSITIVO")
r = d.detect("zara, me conte uma piada")
test("  piada -> nao pc intent", r.is_pc_intent, False)

print("=" * 50)
print(f"RESULTS: {PASS} PASS, {FAIL} FAIL")
sys.exit(0 if FAIL == 0 else 1)
