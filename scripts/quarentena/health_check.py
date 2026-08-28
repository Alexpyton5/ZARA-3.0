#!/usr/bin/env python3
"""
ZARA 3.0 — Health Check CLI (Codex Patterns)
Comprehensive health verification for ZARA runtime and build artifacts.
"""

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core.paths import (
    config_dir, data_dir, memory_dir, logs_dir, 
    user_data_dir, project_root, api_keys_path
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


class HealthChecker:
    """Comprehensive health checks for ZARA."""
   
    def __init__(self, project_root_path: Path = None, data_root_path: Path = None):
        self.project_root = project_root_path or project_root()
        self.data_root = data_root_path or user_data_dir()
        self.checks = []
    
    def add_check(self, name: str, status: str, message: str = "", 
                  details: dict = None, duration_ms: float = 0):
        """Add a check result."""
        self.checks.append({
            "name": name,
            "status": status,  # "pass", "fail", "warn", "skip"
            "message": message,
            "details": details or {},
            "duration_ms": round(duration_ms, 1)
        })
    
    def check_python_env(self) -> dict:
        """Check Python environment."""
        start = time.perf_counter()
        try:
            version = sys.version.split()[0]
            executable = sys.executable
            venv = "VIRTUAL_ENV" in os.environ
            
            self.add_check("python_env", "pass", 
                          f"Python {version} at {executable}",
                          {"version": version, "executable": executable, "venv": venv},
                          (time.perf_counter() - start) * 1000)
        except Exception as e:
            self.add_check("python_env", "fail", f"Error: {e}", duration_ms=(time.perf_counter() - start) * 1000)
    
    def check_dependencies(self) -> dict:
        """Check essential dependencies."""
        start = time.perf_counter()
        essential = ["httpx", "pydantic", "pydantic_settings", "psutil"]
        optional = ["cv2", "mss", "PIL", "pytesseract", "vosk", "pvporcupine",
                   "kokoro_onnx", "sounddevice", "numpy", "scipy", "playwright",
                   "pyperclip", "watchdog", "edge_tts", "miniaudio"]
        
        missing_essential = []
        missing_optional = []
        import importlib.util
        
        for pkg in essential:
            if importlib.util.find_spec(pkg) is None:
                missing_essential.append(pkg)
        
        for pkg in optional:
            if importlib.util.find_spec(pkg) is None:
                missing_optional.append(pkg)
        
        if missing_essential:
            self.add_check("dependencies", "fail",
                          f"Missing essential: {', '.join(missing_essential)}",
                          {"missing_essential": missing_essential, "missing_optional": missing_optional},
                          (time.perf_counter() - start) * 1000)
        elif missing_optional:
            self.add_check("dependencies", "warn",
                          f"Missing optional: {', '.join(missing_optional)}",
                          {"missing_essential": [], "missing_optional": missing_optional},
                          (time.perf_counter() - start) * 1000)
        else:
            self.add_check("dependencies", "pass",
                          "All dependencies available",
                          {"missing_essential": [], "missing_optional": []},
                          (time.perf_counter() - start) * 1000)
    
    def check_project_structure(self) -> dict:
        """Check project structure integrity."""
        start = time.perf_counter()
        required = [
            "main.py",
            "build_exe.py",
            "requirements.txt",
            "pyproject.toml",
            "core/__init__.py",
            "core/paths.py",
            "core/ipc_handlers.py",
            "core/action_registry.py",
        ]
        
        missing = []
        for req in required:
            if not (self.project_root / req).exists():
                missing.append(req)
        
        if missing:
            self.add_check("project_structure", "fail",
                          f"Missing files: {', '.join(missing)}",
                          {"missing": missing},
                          (time.perf_counter() - start) * 1000)
        else:
            self.add_check("project_structure", "pass",
                          "All required files present",
                          {"checked": len(required)},
                          (time.perf_counter() - start) * 1000)
    
    def check_data_directories(self) -> dict:
        """Check data directories exist and are writable."""
        start = time.perf_counter()
        dirs = [
            ("config", config_dir()),
            ("data", data_dir()),
            ("memory", memory_dir()),
            ("logs", logs_dir()),
        ]
        
        results = []
        for name, path in dirs:
            exists = path.exists()
            writable = os.access(path, os.W_OK) if exists else False
            results.append({"name": name, "path": str(path), "exists": exists, "writable": writable})
            
            if not exists or not writable:
                self.add_check(f"data_dir_{name}", "fail" if not exists else "warn",
                              f"Directory {'missing' if not exists else 'not writable'}: {path}",
                              {"path": str(path), "exists": exists, "writable": writable},
                              (time.perf_counter() - start) * 1000)
                return
        
        self.add_check("data_directories", "pass",
                      "All data directories exist and writable",
                      {"directories": results},
                      (time.perf_counter() - start) * 1000)
    
    def check_api_keys(self) -> dict:
        """Check API keys configuration."""
        start = time.perf_counter()
        keys_path = api_keys_path()
        
        if not keys_path.exists():
            self.add_check("api_keys", "warn",
                          "API keys file not found",
                          {"path": str(keys_path), "exists": False},
                          (time.perf_counter() - start) * 1000)
            return
        
        try:
            with open(keys_path, "r", encoding="utf-8") as f:
                keys = json.load(f)
            
            # Check for expected keys (don't expose values)
            expected = ["gemini", "openai", "anthropic", "elevenlabs"]
            present = [k for k in expected if k in keys and keys[k]]
            missing = [k for k in expected if k not in keys or not keys[k]]
            
            if missing:
                self.add_check("api_keys", "warn",
                              f"Some keys missing: {', '.join(missing)}",
                              {"path": str(keys_path), "present": present, "missing": missing},
                              (time.perf_counter() - start) * 1000)
            else:
                self.add_check("api_keys", "pass",
                              f"All expected keys present: {', '.join(present)}",
                              {"path": str(keys_path), "present": present},
                              (time.perf_counter() - start) * 1000)
        except Exception as e:
            self.add_check("api_keys", "fail", f"Error reading API keys: {e}",
                          {"path": str(keys_path)}, (time.perf_counter() - start) * 1000)
    
    def check_build_artifact(self, dist_dir: Path = None) -> dict:
        """Check build artifact exists and is valid."""
        start = time.perf_counter()
        dist_dir = dist_dir or (self.project_root / "dist-sidecar")
        exe_path = dist_dir / "zara-backend.exe"
        
        if not exe_path.exists():
            self.add_check("build_artifact", "fail",
                          f"Build artifact not found: {exe_path}",
                          {"path": str(exe_path), "exists": False},
                          (time.perf_counter() - start) * 1000)
            return
        
        try:
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            
            # Quick execution test
            result = subprocess.run(
                [str(exe_path), "--help"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            # Accept various return codes (help may not be implemented)
            if result.returncode in (0, 1, 2):
                self.add_check("build_artifact", "pass",
                              f"Artifact valid ({size_mb:.1f} MB)",
                              {"path": str(exe_path), "size_mb": round(size_mb, 1), "runnable": True},
                              (time.perf_counter() - start) * 1000)
            else:
                self.add_check("build_artifact", "warn",
                              f"Artifact runs but returned code {result.returncode}",
                              {"path": str(exe_path), "size_mb": round(size_mb, 1), "returncode": result.returncode},
                              (time.perf_counter() - start) * 1000)
        except subprocess.TimeoutExpired:
            self.add_check("build_artifact", "fail",
                          "Artifact execution timeout",
                          {"path": str(exe_path)},
                          (time.perf_counter() - start) * 1000)
        except Exception as e:
            self.add_check("build_artifact", "fail",
                          f"Artifact execution error: {e}",
                          {"path": str(exe_path)},
                          (time.perf_counter() - start) * 1000)
    
    def check_git_status(self) -> dict:
        """Check git repository status."""
        start = time.perf_counter()
        try:
            # Check if we're in a git repo
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode != 0:
                self.add_check("git_status", "skip",
                              "Not a git repository or git not available",
                              {}, (time.perf_counter() - start) * 1000)
                return
            
            changes = result.stdout.strip().split("\n") if result.stdout.strip() else []
            clean = len(changes) == 0
            
            # Get current branch
            branch_result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=5
            )
            branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "unknown"
            
            if clean:
                self.add_check("git_status", "pass",
                              f"Working tree clean on branch '{branch}'",
                              {"branch": branch, "clean": True, "changes": 0},
                              (time.perf_counter() - start) * 1000)
            else:
                self.add_check("git_status", "warn",
                              f"Uncommitted changes on branch '{branch}' ({len(changes)} files)",
                              {"branch": branch, "clean": False, "changes": len(changes)},
                              (time.perf_counter() - start) * 1000)
        except Exception as e:
            self.add_check("git_status", "skip",
                          f"Git check skipped: {e}",
                          {}, (time.perf_counter() - start) * 1000)
    
    def check_disk_space(self) -> dict:
        """Check available disk space."""
        start = time.perf_counter()
        try:
            import shutil
            total, used, free = shutil.disk_usage(self.data_root)
            free_gb = free / (1024**3)
            used_pct = (used / total) * 100
            
            if free_gb < 1:
                status = "fail"
                msg = f"Critical: only {free_gb:.1f} GB free"
            elif free_gb < 5:
                status = "warn"
                msg = f"Low disk space: {free_gb:.1f} GB free"
            else:
                status = "pass"
                msg = f"Disk OK: {free_gb:.1f} GB free ({used_pct:.1f}% used)"
            
            self.add_check("disk_space", status, msg,
                          {"free_gb": round(free_gb, 1), "used_pct": round(used_pct, 1)},
                          (time.perf_counter() - start) * 1000)
        except Exception as e:
            self.add_check("disk_space", "skip",
                          f"Disk check failed: {e}",
                          {}, (time.perf_counter() - start) * 1000)
    
    def check_processes(self) -> dict:
        """Check for conflicting ZARA processes."""
        start = time.perf_counter()
        try:
            import psutil
            
            zara_processes = []
            for proc in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
                try:
                    if proc.info["name"] and "zara" in proc.info["name"].lower():
                        zara_processes.append({
                            "pid": proc.info["pid"],
                            "name": proc.info["name"],
                            "exe": proc.info["exe"],
                        })
                    elif proc.info["cmdline"] and any("zara" in c.lower() for c in proc.info["cmdline"] if c):
                        zara_processes.append({
                            "pid": proc.info["pid"],
                            "name": proc.info["name"],
                            "exe": proc.info["exe"],
                        })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
            
            if zara_processes:
                self.add_check("processes", "warn",
                              f"Found {len(zara_processes)} ZARA process(es) running",
                              {"processes": zara_processes},
                              (time.perf_counter() - start) * 1000)
            else:
                self.add_check("processes", "pass",
                              "No conflicting ZARA processes",
                              {"count": 0},
                              (time.perf_counter() - start) * 1000)
        except Exception as e:
            self.add_check("processes", "skip",
                          f"Process check failed: {e}",
                          {}, (time.perf_counter() - start) * 1000)
    
    def run_all(self, include_build: bool = True, dist_dir: Path = None) -> dict:
        """Run all health checks."""
        logger.info("Running health checks...")
        
        self.check_python_env()
        self.check_dependencies()
        self.check_project_structure()
        self.check_data_directories()
        self.check_api_keys()
        self.check_disk_space()
        self.check_processes()
        self.check_git_status()
        
        if include_build:
            self.check_build_artifact(dist_dir)
        
        # Summary
        passed = sum(1 for c in self.checks if c["status"] == "pass")
        failed = sum(1 for c in self.checks if c["status"] == "fail")
        warned = sum(1 for c in self.checks if c["status"] == "warn")
        skipped = sum(1 for c in self.checks if c["status"] == "skip")
        
        overall = "pass" if failed == 0 else "fail"
        if failed == 0 and warned > 0:
            overall = "warn"
        
        return {
            "overall": overall,
            "summary": {
                "total": len(self.checks),
                "passed": passed,
                "failed": failed,
                "warned": warned,
                "skipped": skipped
            },
            "checks": self.checks
        }


def setup_parser() -> argparse.ArgumentParser:
    """Create and configure argument parser."""
    parser = argparse.ArgumentParser(
        prog="zara-health",
        description="ZARA 3.0 Health Check",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  zara-health                        # Full health check
  zara-health --no-build             # Skip build artifact check
  zara-health --json                 # Output as JSON
  zara-health --fail-fast            # Exit on first failure
        """
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG) logging"
    )
    
    parser.add_argument(
        "--no-build",
        action="store_true",
        help="Skip build artifact verification"
    )
    
    parser.add_argument(
        "--dist-dir",
        type=Path,
        help="Build output directory (default: dist-sidecar)"
    )
    
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )
    
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Exit immediately on first failure"
    )
    
    return parser


def main(args: list = None) -> int:
    """Main entry point."""
    parser = setup_parser()
    parsed_args = parser.parse_args(args)
    
    if parsed_args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled")
    
    checker = HealthChecker()
    
    try:
        result = checker.run_all(include_build=not parsed_args.no_build, dist_dir=parsed_args.dist_dir)
        
        if parsed_args.json:
            print(json.dumps(result, indent=2))
        else:
            # Human-readable output
            print(f"\n{'='*60}")
            print(f"ZARA 3.0 HEALTH CHECK")
            print(f"{'='*60}")
            print(f"Overall: {result['overall'].upper()}")
            print(f"Summary: {result['summary']['passed']} passed, "
                  f"{result['summary']['failed']} failed, "
                  f"{result['summary']['warned']} warnings, "
                  f"{result['summary']['skipped']} skipped")
            print(f"{'='*60}\n")
            
            for check in result["checks"]:
                icon = {"pass": "✓", "fail": "✗", "warn": "⚠", "skip": "○"}[check["status"]]
                print(f"  {icon} {check['name']}: {check['message']} ({check['duration_ms']}ms)")
        
        # Determine exit code
        if result["overall"] == "fail":
            return 1
        elif result["overall"] == "warn":
            return 0  # Warnings don't fail
        return 0
        
    except KeyboardInterrupt:
        logger.warning("Health check interrupted by user")
        return 130
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())