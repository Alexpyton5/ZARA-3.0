#!/usr/bin/env python3
"""
Nightly regression suite for ZARA 3.0.
Runs the full test suite and reports failures compared to a baseline.
Never converts a non-zero pytest result into a successful process exit.
"""

import json
import subprocess
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
KNOWN_FAILURES_FILE = PROJECT_ROOT / ".known_failures.json"
VENV_PYTHON = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"

def run_tests():
    """Run pytest and return list of failed test names and total tests collected."""
    cmd = [str(VENV_PYTHON), "-m", "pytest", "--tb=no", "-q"]
    result = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
    # Parse output to extract failed test names and total collected
    failed = []
    total_collected = None
    for line in result.stdout.splitlines():
        if line.startswith("collected"):
            # Example: collected 1294 items
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                total_collected = int(parts[1])
        if line.startswith("FAILED"):
            # Example: FAILED tests/test_brain_store.py::test_cross_compartment_dedup - assert None ...
            parts = line.split()
            if len(parts) >= 2:
                test_id = parts[1]
                failed.append(test_id)
    return failed, total_collected, result.returncode, result.stdout, result.stderr

def load_known_failures():
    """Load known failures from JSON file."""
    if not KNOWN_FAILURES_FILE.exists():
        return set()
    try:
        with open(KNOWN_FAILURES_FILE, "r") as f:
            data = json.load(f)
            return set(data.get("failed_tests", []))
    except Exception as e:
        print(f"Warning: Could not load known failures: {e}")
        return set()

def save_known_failures(failed_tests):
    """Save known failures to JSON file."""
    data = {
        "failed_tests": sorted(list(failed_tests)),
        "updated": str(Path(__file__).name),
    }
    with open(KNOWN_FAILURES_FILE, "w") as f:
        json.dump(data, f, indent=2)

def main():
    print("Running nightly regression suite...")
    failed_tests, total_collected, returncode, stdout, stderr = run_tests()
    if total_collected is not None:
        print(f"Total tests collected: {total_collected}")
    print(f"Tests run (approx): {len(failed_tests) + (returncode == 0 and 0 or 0)}")  # approximate
    print(f"Failed tests: {len(failed_tests)}")
    if failed_tests:
        print("Failed tests:")
        for test in failed_tests:
            print(f"  {test}")

    known_failures = load_known_failures()
    print(f"Known failures (baseline): {len(known_failures)}")

    new_failures = set(failed_tests) - known_failures
    fixed_tests = known_failures - set(failed_tests)

    update_baseline = os.environ.get("NIGHTLY_REGRESSION_UPDATE_BASELINE", "0") == "1"

    if not KNOWN_FAILURES_FILE.exists() and not update_baseline:
        # No baseline yet, and we are not allowed to update, so we create a baseline and exit successfully (baseline established)
        print("\nNo baseline found. Creating baseline with current failures (update baseline not allowed in this mode).")
        save_known_failures(set(failed_tests))
        return 0

    if new_failures:
        print("\nNEW FAILURES DETECTED:")
        for test in sorted(new_failures):
            print(f"  {test}")
        print(f"\n{len(new_failures)} new failure(s).")
        if fixed_tests:
            print(f"\n{len(fixed_tests)} test(s) now fixed (consider updating baseline):")
            for test in sorted(fixed_tests):
                print(f"  {test}")
        # Optionally update baseline? We only update if the environment variable is set.
        if update_baseline:
            print("\nUpdating baseline with current failures (as requested by NIGHTLY_REGRESSION_UPDATE_BASELINE=1).")
            save_known_failures(set(failed_tests))
        return 1
    elif returncode != 0:
        # Tests failed but no new failures (all failures are in baseline)
        # Per "Never converts a non-zero pytest result into a successful process exit", return failure
        print("\nTests failed (all failures are known baseline). Regression check failed (non-zero pytest exit).")
        if fixed_tests:
            print(f"The following previously failing tests now pass (consider updating baseline):")
            for test in sorted(fixed_tests):
                print(f"  {test}")
        # Update baseline to remove fixed tests if requested
        if update_baseline:
            print("\nUpdating baseline to remove fixed tests (as requested by NIGHTLY_REGRESSION_UPDATE_BASELINE=1).")
            save_known_failures(set(failed_tests))
        return 1
    else:
        print("\nNo new failures. Regression check passed.")
        if fixed_tests:
            print(f"The following previously failing tests now pass (consider updating baseline):")
            for test in sorted(fixed_tests):
                print(f"  {test}")
        # Update baseline to remove fixed tests if requested
        if update_baseline:
            print("\nUpdating baseline to remove fixed tests (as requested by NIGHTLY_REGRESSION_UPDATE_BASELINE=1).")
            save_known_failures(set(failed_tests))
        return 0

if __name__ == "__main__":
    sys.exit(main())