#!/usr/bin/env python3
"""
ZARA 3.0 — Sync CLI (Codex Patterns)
Sync configurations, data, and state between environments.
"""

import argparse
import json
import logging
import os
import shutil
import sys
from datetime import datetime
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


class SyncManager:
    """Manages synchronization of ZARA configurations and data."""
    
    def __init__(self, source_root: Path = None, target_root: Path = None):
        self.source_root = source_root or project_root()
        self.target_root = target_root or user_data_dir()
        
        # Define sync pairs: (source_rel, target_rel, description)
        self.sync_items = [
            # Config files
            ("config", "config", "Configuration files"),
            # Data files
            ("data", "data", "Runtime data"),
            # Memory (optional - large)
            ("memory", "memory", "Memory databases"),
            # Logs (optional - large)
            ("logs", "logs", "Log files"),
        ]
    
    def get_size(self, path: Path) -> int:
        """Get total size of directory in bytes."""
        if not path.exists():
            return 0
        total = 0
        for f in path.rglob("*"):
            if f.is_file():
                total += f.stat().st_size
        return total
    
    def format_size(self, bytes_: int) -> str:
        """Format bytes as human readable."""
        for unit in ["B", "KB", "MB", "GB"]:
            if bytes_ < 1024:
                return f"{bytes_:.1f} {unit}"
            bytes_ /= 1024
        return f"{bytes_:.1f} TB"
    
    def sync_item(self, src: Path, dst: Path, description: str, dry_run: bool = False) -> dict:
        """Sync a single item (file or directory)."""
        if not src.exists():
            return {"status": "skipped", "reason": f"Source not found: {src}"}
        
        src_size = self.get_size(src) if src.is_dir() else src.stat().st_size
        
        if dry_run:
            return {
                "status": "would_sync",
                "source": str(src),
                "target": str(dst),
                "size": self.format_size(src_size),
                "description": description
            }
        
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            
            if src.is_dir():
                # Use copytree with dirs_exist_ok for Python 3.8+
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
            
            return {
                "status": "synced",
                "source": str(src),
                "target": str(dst),
                "size": self.format_size(src_size),
                "description": description
            }
        except Exception as e:
            return {
                "status": "failed",
                "source": str(src),
                "target": str(dst),
                "error": str(e),
                "description": description
            }
    
    def sync_all(self, include_memory: bool = False, include_logs: bool = False, 
                 dry_run: bool = False, direction: str = "source_to_target") -> dict:
        """Sync all configured items."""
        results = []
        total_synced = 0
        total_failed = 0
        total_skipped = 0
        
        for src_rel, dst_rel, desc in self.sync_items:
            # Skip optional items if not requested
            if src_rel == "memory" and not include_memory:
                results.append({"status": "skipped", "reason": "Use --include-memory to sync", "description": desc})
                total_skipped += 1
                continue
            if src_rel == "logs" and not include_logs:
                results.append({"status": "skipped", "reason": "Use --include-logs to sync", "description": desc})
                total_skipped += 1
                continue
            
            if direction == "source_to_target":
                src = self.source_root / src_rel
                dst = self.target_root / dst_rel
            else:
                src = self.target_root / src_rel
                dst = self.source_root / dst_rel
            
            result = self.sync_item(src, dst, desc, dry_run)
            results.append(result)
            
            if result["status"] in ("synced", "would_sync"):
                total_synced += 1
            elif result["status"] == "failed":
                total_failed += 1
            else:
                total_skipped += 1
        
        return {
            "direction": direction,
            "dry_run": dry_run,
            "summary": {
                "synced": total_synced,
                "failed": total_failed,
                "skipped": total_skipped
            },
            "items": results
        }
    
    def sync_api_keys(self, dry_run: bool = False, direction: str = "source_to_target") -> dict:
        """Sync API keys specifically."""
        if direction == "source_to_target":
            src = self.source_root / "config" / "api_keys.json"
            dst = api_keys_path()
        else:
            src = api_keys_path()
            dst = self.source_root / "config" / "api_keys.json"
        
        if not src.exists():
            return {"status": "skipped", "reason": f"Source not found: {src}"}
        
        if dry_run:
            return {
                "status": "would_sync",
                "source": str(src),
                "target": str(dst),
                "size": self.format_size(src.stat().st_size),
                "description": "API Keys"
            }
        
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            return {
                "status": "synced",
                "source": str(src),
                "target": str(dst),
                "size": self.format_size(src.stat().st_size),
                "description": "API Keys"
            }
        except Exception as e:
            return {"status": "failed", "error": str(e), "description": "API Keys"}
    
    def verify_sync(self) -> dict:
        """Verify sync integrity by comparing key files."""
        results = []
        
        check_files = [
            ("config/api_keys.json", "API Keys"),
            ("config/settings.json", "Settings"),
        ]
        
        for rel, desc in check_files:
            src = self.source_root / rel
            dst = self.target_root / rel
            
            if not src.exists() and not dst.exists():
                results.append({"file": rel, "status": "both_missing", "description": desc})
                continue
            
            if src.exists() and dst.exists():
                src_hash = self._file_hash(src)
                dst_hash = self._file_hash(dst)
                if src_hash == dst_hash:
                    results.append({"file": rel, "status": "matched", "description": desc})
                else:
                    results.append({"file": rel, "status": "mismatched", "description": desc})
            elif src.exists():
                results.append({"file": rel, "status": "only_source", "description": desc})
            else:
                results.append({"file": rel, "status": "only_target", "description": desc})
        
        return {"verification": results}
    
    def _file_hash(self, path: Path) -> str:
        """Compute SHA256 hash of a file."""
        import hashlib
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()


def setup_parser() -> argparse.ArgumentParser:
    """Create and configure argument parser."""
    parser = argparse.ArgumentParser(
        prog="zara-sync",
        description="ZARA 3.0 Configuration & Data Sync",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  zara-sync                          # Sync config + data (source -> target)
  zara-sync --include-memory         # Also sync memory databases
  zara-sync --include-logs           # Also sync log files
  zara-sync --reverse                # Sync target -> source (pull)
  zara-sync --dry-run                # Preview what would be synced
  zara-sync --api-keys               # Only sync API keys
  zara-sync --verify                 # Verify sync integrity
        """
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG) logging"
    )
    
    parser.add_argument(
        "--source-root",
        type=Path,
        help="Source root directory (default: project root)"
    )
    
    parser.add_argument(
        "--target-root",
        type=Path,
        help="Target root directory (default: user data dir)"
    )
    
    parser.add_argument(
        "--include-memory",
        action="store_true",
        help="Include memory databases in sync"
    )
    
    parser.add_argument(
        "--include-logs",
        action="store_true",
        help="Include log files in sync"
    )
    
    parser.add_argument(
        "--reverse",
        action="store_true",
        help="Sync from target to source (pull instead of push)"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without executing"
    )
    
    parser.add_argument(
        "--api-keys",
        action="store_true",
        help="Only sync API keys"
    )
    
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify sync integrity"
    )
    
    return parser


def main(args: list = None) -> int:
    """Main entry point."""
    parser = setup_parser()
    parsed_args = parser.parse_args(args)
    
    if parsed_args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled")
    
    manager = SyncManager(
        source_root=parsed_args.source_root,
        target_root=parsed_args.target_root
    )
    
    try:
        if parsed_args.verify:
            result = manager.verify_sync()
            print(json.dumps(result, indent=2))
            return 0
        
        if parsed_args.api_keys:
            result = manager.sync_api_keys(dry_run=parsed_args.dry_run, 
                                          direction="target_to_source" if parsed_args.reverse else "source_to_target")
            print(json.dumps(result, indent=2))
            return 0 if result["status"] in ("synced", "would_sync") else 1
        
        direction = "target_to_source" if parsed_args.reverse else "source_to_target"
        result = manager.sync_all(
            include_memory=parsed_args.include_memory,
            include_logs=parsed_args.include_logs,
            dry_run=parsed_args.dry_run,
            direction=direction
        )
        
        print(json.dumps(result, indent=2))
        
        if result["summary"]["failed"] > 0:
            return 1
        return 0
        
    except KeyboardInterrupt:
        logger.warning("Sync interrupted by user")
        return 130
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())