#!/usr/bin/env python3
"""Test runner for ZARA 3.0 - runs all test suites with proper configuration."""

import subprocess
import sys
import os

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(PROJECT_ROOT, ".venv", "Scripts", "python.exe")


def run_cmd(cmd_list, description):
    """Run a command and return success status. Uses list args (no shell)."""
    print(f"\n{'='*60}")
    print(f"RUNNING: {description}")
    print(f"CMD: {' '.join(cmd_list)}")
    print(f"{'='*60}\n")
    result = subprocess.run(cmd_list, cwd=PROJECT_ROOT)
    return result.returncode == 0


def main():
    os.chdir(PROJECT_ROOT)

    # Check venv exists
    if not os.path.exists(VENV_PYTHON):
        print(f"ERROR: Venv not found at {VENV_PYTHON}")
        print("Run: python -m venv .venv && .venv/Scripts/pip install -e .[dev]")
        return 1

    results = {}

    # 1. Lint
    results["lint"] = run_cmd(
        [VENV_PYTHON, "-m", "ruff", "check", "core", "memory", "integrations", "tests", "--output-format=concise"],
        "Ruff Lint Check"
    )

    # 2. Format check
    results["format"] = run_cmd(
        [VENV_PYTHON, "-m", "ruff", "format", "--check", "core", "memory", "integrations", "tests"],
        "Ruff Format Check"
    )

    # 3. Unit tests
    results["unit"] = run_cmd(
        [VENV_PYTHON, "-m", "pytest", "-q", "--tb=short"],
        "All Unit Tests"
    )

    # 4. Voice tests
    results["voice"] = run_cmd(
        [VENV_PYTHON, "-m", "pytest", "-k", "voice", "-q", "--tb=short"],
        "Voice Tests"
    )

    # 5. Media tests
    results["media"] = run_cmd(
        [VENV_PYTHON, "-m", "pytest", "-k", "media", "-q", "--tb=short"],
        "Media Tests"
    )

    # 6. Relay tests
    results["relay"] = run_cmd(
        [VENV_PYTHON, "-m", "pytest", "-k", "relay", "-q", "--tb=short"],
        "Relay Tests"
    )

    # 7. Coverage
    results["coverage"] = run_cmd(
        [VENV_PYTHON, "-m", "pytest", "--cov=core", "--cov=memory", "--cov=integrations", "--cov-report=term-missing"],
        "Coverage Report"
    )

    # Summary
    print("\n" + "="*60)
    print("TEST RUN SUMMARY")
    print("="*60)
    all_passed = True
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  {name:12s} : {status}")
        if not passed:
            all_passed = False

    print("="*60)
    if all_passed:
        print("ALL TESTS PASSED")
        return 0
    else:
        print("SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())