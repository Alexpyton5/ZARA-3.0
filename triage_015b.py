import sys, os, time, json, psutil
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.chdir(os.path.dirname(os.path.abspath(__file__)))
import core.actions.os_ops as os_ops

report = {}

def clean(apps):
    for name in apps:
        for p in psutil.process_iter(["pid","name"]):
            try:
                if p.info["name"] and p.info["name"].lower() in {a.lower() for a in apps}:
                    p.terminate()
                    report.setdefault("CLEANED", []).append((p.info["pid"], p.info["name"]))
            except Exception:
                pass

# open notepad (has real hwnd)
np = os_ops.os_app_action("notepad")
report["NOTEPAD_OPEN"] = (np.success, np.data.get("hwnd"), np.data.get("window_pid")) if np.success else (np.success, np.error)
hwnd = np.data.get("hwnd") if np.success else None

if hwnd:
    wmin = os_ops.window_minimize_action(hwnd=hwnd)
    report["6_MIN"] = (wmin.success, wmin.error, wmin.data.get("before"), wmin.data.get("after")) if wmin.success else (wmin.success, wmin.error)
    time.sleep(0.2)
    wmax = os_ops.window_maximize_action(hwnd=hwnd)
    report["6_MAX"] = (wmax.success, wmax.error, wmax.data.get("before"), wmax.data.get("after")) if wmax.success else (wmax.success, wmax.error)
    time.sleep(0.2)
    wres = os_ops.window_restore_action(hwnd=hwnd)
    report["6_RESTORE"] = (wres.success, wres.error, wres.data.get("before"), wres.data.get("after")) if wres.success else (wres.success, wres.error)
else:
    report["6"] = "NO_HWND"

# cleanup notepad + any leftover calc
clean(["notepad.exe", "calculator.exe", "calculatorapp.exe"])
time.sleep(0.5)
# verify none left
left = []
for p in psutil.process_iter(["pid","name"]):
    try:
        if p.info["name"] and p.info["name"].lower() in {"notepad.exe","calculator.exe","calculatorapp.exe"}:
            left.append((p.info["pid"], p.info["name"]))
    except Exception:
        pass
report["LEFTOVER"] = left

print(json.dumps(report, default=str, indent=2))
