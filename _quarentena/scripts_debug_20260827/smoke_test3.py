import os
import sys
import time
import subprocess

exe_path = os.path.join(os.getcwd(), "dist-sidecar", "zara-backend.exe")
print("Exe path:", exe_path)
print("Exists:", os.path.exists(exe_path))

if not os.path.exists(exe_path):
    print("ERROR: Exe not found")
    sys.exit(1)

print(f"Starting {exe_path} and capturing output...")
try:
    # Start the process, redirecting stdout and stderr to pipes
    proc = subprocess.Popen([exe_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE)
    # Wait for 5 seconds to see output
    time.sleep(5)
    # If it's still running, terminate it
    if proc.poll() is None:
        print("Terminating process...")
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            print("Process did not terminate, killing...")
            proc.kill()
            proc.wait()
    # Get the output
    outs, errs = proc.communicate()
    print("=== STDOUT ===")
    print(outs.decode('utf-8', errors='replace'))
    print("=== STDERR ===")
    print(errs.decode('utf-8', errors='replace'))
    print(f"Return code: {proc.returncode}")
except Exception as e:
    print(f"Error running {exe_path}: {e}")
    sys.exit(1)