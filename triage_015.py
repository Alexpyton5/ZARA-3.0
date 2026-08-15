import sys, os, time, json, traceback
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.chdir(os.path.dirname(os.path.abspath(__file__)))

import core.actions.os_ops as os_ops
from core.action_registry import ActionResult

report = {}

def safe(call, name):
    try:
        r = call()
        return r
    except Exception as e:
        return ActionResult(success=False, error=f"EXC {type(e).__name__}: {e}")

# 1. VOLUME
try:
    # read original via pycaw scalar
    from comtypes import CLSCTX_ALL, CoInitialize, CoUninitialize
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    CoInitialize()
    try:
        dev = AudioUtilities.GetSpeakers().Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None).QueryInterface(IAudioEndpointVolume)
        orig = round(dev.GetMasterVolumeLevelScalar()*100)
    finally:
        CoUninitialize()
except Exception as e:
    orig = f"READ_ERR {e}"
report["1_VOLUME_ORIGINAL"] = orig
vr = safe(lambda: os_ops.os_volume_action(level=70), "vol_set70")
report["1_VOLUME_SET70"] = (vr.success, vr.error, vr.data)
# readback
try:
    CoInitialize()
    try:
        dev = AudioUtilities.GetSpeakers().Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None).QueryInterface(IAudioEndpointVolume)
        rb = round(dev.GetMasterVolumeLevelScalar()*100)
    finally:
        CoUninitialize()
except Exception as e:
    rb = f"RB_ERR {e}"
report["1_VOLUME_READBACK"] = rb
# restore
if isinstance(orig, int):
    rr = safe(lambda: os_ops.os_volume_action(level=orig), "vol_restore")
    report["1_VOLUME_RESTORE"] = (rr.success, rr.error)
    try:
        CoInitialize()
        try:
            dev = AudioUtilities.GetSpeakers().Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None).QueryInterface(IAudioEndpointVolume)
            final = round(dev.GetMasterVolumeLevelScalar()*100)
        finally:
            CoUninitialize()
    except Exception as e:
        final = f"F_ERR {e}"
    report["1_VOLUME_FINAL"] = final

# 2. MUTE/UNMUTE
mr = safe(os_ops.audio_mute_action, "mute")
report["2_MUTE"] = (mr.success, mr.error, mr.data)
ur = safe(os_ops.audio_unmute_action, "unmute")
report["2_UNMUTE"] = (ur.success, ur.error, ur.data)

# 3. BRIGHTNESS (DDC/CI) - read only first
br = safe(os_ops.os_brightness_action, "brightness_read")
report["3_BRIGHTNESS_READ"] = (br.success, br.error, br.data)

# 4. NIGHT LIGHT (declared unsupported)
nl = safe(os_ops.os_night_light_on_action, "nightlight")
report["4_NIGHTLIGHT"] = (nl.success, nl.error, nl.data)

# 5. OPEN CALC then NOTEPAD, capture PIDs
calc = safe(lambda: os_ops.os_app_action("calculator"), "calc")
report["5_CALC"] = (calc.success, calc.error, calc.data)
time.sleep(0.5)
notepad = safe(lambda: os_ops.os_app_action("notepad"), "notepad")
report["5_NOTEPAD"] = (notepad.success, notepad.error, notepad.data)
# close created processes
import subprocess, psutil
created = set()
for res in (calc, notepad):
    if res.success and res.data:
        created.update(res.data.get("created_pids", []))
report["5_CREATED_PIDS"] = sorted(created)
for pid in created:
    try:
        p = psutil.Process(pid)
        p.terminate()
        report.setdefault("5_CLOSED", []).append(pid)
    except Exception as e:
        report.setdefault("5_CLOSE_ERR", []).append(str(e))

# 6. WINDOW MIN/MAX/RESTORE on a test window (use calc hwnd)
hwnd = None
if calc.success and calc.data:
    hwnd = calc.data.get("hwnd")
if hwnd:
    wmin = safe(lambda: os_ops.window_minimize_action(hwnd=hwnd), "win_min")
    report["6_WIN_MIN"] = (wmin.success, wmin.error, wmin.data)
    wmax = safe(lambda: os_ops.window_maximize_action(hwnd=hwnd), "win_max")
    report["6_WIN_MAX"] = (wmax.success, wmax.error, wmax.data)
    wres = safe(lambda: os_ops.window_restore_action(hwnd=hwnd), "win_res")
    report["6_WIN_RESTORE"] = (wres.success, wres.error, wres.data)
else:
    report["6_WIN"] = "NO_HWND"

print(json.dumps(report, default=str, indent=2))
