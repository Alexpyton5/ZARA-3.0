import subprocess
import sys
import time

exe_path = "dist-sidecar/zara-backend.exe"
print(f"Starting {exe_path}...")
try:
    # Start the process
    proc = subprocess.Popen([exe_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE)
    # Wait for 2 seconds to see if it starts and prints the banner
    time.sleep(2)
    # If it's still running, terminate it
    if proc.poll() is None:
        proc.terminate()
        # Wait a bit more for termination
        proc.wait(timeout=1)
    # Get the output
    outs, errs = proc.communicate()
    print("STDOUT:")
    print(outs.decode('utf-8', errors='replace'))
    print("STDERR:")
    print(errs.decode('utf-8', errors='replace'))
    print(f"Return code: {proc.returncode}")
except Exception as e:
    print(f"Error running {exe_path}: {e}")
    sys.exit(1)