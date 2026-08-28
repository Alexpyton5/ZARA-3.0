#!/usr/bin/env python3
"""
ZARA 3.0 — Deploy CLI (Codex Patterns)
Deploy built artifacts with verification, staging, and rollback support.
"""

import argparse
import hashlib
import json
import logging
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


class DeployManager:
    """Manages deployment of ZARA sidecar artifacts."""
    
    def __init__(self, dist_dir: Path, target_dir: Path, staging_dir: Path = None):
        self.dist_dir = dist_dir
        self.target_dir = target_dir
        self.staging_dir = staging_dir or (target_dir.parent / "staging")
        self.manifest_path = self.staging_dir / "deploy_manifest.json"
        
    def compute_hash(self, file_path: Path) -> str:
        """Compute SHA256 hash of a file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def verify_artifact(self, exe_path: Path) -> dict:
        """Verify a built artifact."""
        if not exe_path.exists():
            return {"valid": False, "error": f"File not found: {exe_path}"}
        
        try:
            # Quick size check
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            if size_mb < 1 or size_mb > 200:
                return {"valid": False, "error": f"Suspicious size: {size_mb:.1f} MB"}
            
            # Run basic verification
            result = subprocess.run(
                [str(exe_path), "--help"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            # Help flag might not exist, but process should not crash immediately
            if result.returncode not in (0, 1, 2):
                return {"valid": False, "error": f"Process crashed: {result.stderr}"}
            
            return {
                "valid": True,
                "path": str(exe_path),
                "size_mb": round(size_mb, 1),
                "sha256": self.compute_hash(exe_path),
                "verified_at": datetime.utcnow().isoformat() + "Z"
            }
        except subprocess.TimeoutExpired:
            return {"valid": False, "error": "Verification timeout"}
        except Exception as e:
            return {"valid": False, "error": str(e)}
    
    def stage_artifact(self, exe_name: str = "zara-backend.exe") -> dict:
        """Stage artifact for deployment."""
        src = self.dist_dir / exe_name
        if not src.exists():
            return {"success": False, "error": f"Source not found: {src}"}
        
        # Verify before staging
        verification = self.verify_artifact(src)
        if not verification["valid"]:
            return {"success": False, "error": f"Verification failed: {verification['error']}"}
        
        # Create staging directory
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy to staging
        dst = self.staging_dir / exe_name
        shutil.copy2(src, dst)
        
        # Save manifest
        manifest = {
            "artifact": exe_name,
            "source": str(src),
            "staged_path": str(dst),
            "verification": verification,
            "staged_at": datetime.utcnow().isoformat() + "Z"
        }
        
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        
        logger.info(f"Artifact staged: {dst}")
        logger.info(f"SHA256: {verification['sha256']}")
        return {"success": True, "manifest": manifest}
    
    def deploy_staged(self, backup: bool = True) -> dict:
        """Deploy staged artifact to target."""
        if not self.manifest_path.exists():
            return {"success": False, "error": "No staged artifact found. Run stage first."}
        
        with open(self.manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        
        staged_path = Path(manifest["staged_path"])
        if not staged_path.exists():
            return {"success": False, "error": f"Staged artifact missing: {staged_path}"}
        
        target_path = self.target_dir / manifest["artifact"]
        
        # Backup existing if requested
        if backup and target_path.exists():
            backup_path = target_path.with_suffix(f".backup.{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.exe")
            shutil.copy2(target_path, backup_path)
            logger.info(f"Backed up existing: {backup_path}")
            manifest["backup"] = str(backup_path)
        
        # Ensure target directory exists
        self.target_dir.mkdir(parents=True, exist_ok=True)
        
        # Deploy
        shutil.copy2(staged_path, target_path)
        
        # Verify deployed
        verification = self.verify_artifact(target_path)
        if not verification["valid"]:
            # Restore backup if verification fails
            if "backup" in manifest:
                shutil.copy2(manifest["backup"], target_path)
                logger.warning(f"Verification failed, restored backup")
            return {"success": False, "error": f"Deploy verification failed: {verification['error']}"}
        
        manifest["deployed_path"] = str(target_path)
        manifest["deployed_at"] = datetime.utcnow().isoformat() + "Z"
        manifest["deploy_verification"] = verification
        
        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        
        logger.info(f"Deployed to: {target_path}")
        return {"success": True, "manifest": manifest}
    
    def rollback(self) -> dict:
        """Rollback to previous backup."""
        if not self.manifest_path.exists():
            return {"success": False, "error": "No manifest found"}
        
        with open(self.manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        
        if "backup" not in manifest:
            return {"success": False, "error": "No backup available for rollback"}
        
        backup_path = Path(manifest["backup"])
        target_path = Path(manifest["deployed_path"])
        
        if not backup_path.exists():
            return {"success": False, "error": f"Backup missing: {backup_path}"}
        
        shutil.copy2(backup_path, target_path)
        logger.info(f"Rolled back to: {backup_path}")
        return {"success": True, "rolled_back_to": str(backup_path)}


def setup_parser() -> argparse.ArgumentParser:
    """Create and configure argument parser."""
    parser = argparse.ArgumentParser(
        prog="zara-deploy",
        description="ZARA 3.0 Sidecar Deployer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  zara-deploy                          # Stage + deploy (default dirs)
  zara-deploy --stage-only             # Only stage artifact
  zara-deploy --deploy-only            # Deploy already staged
  zara-deploy --rollback               # Rollback to backup
  zara-deploy --target /custom/path    # Custom target directory
        """
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG) logging"
    )
    
    parser.add_argument(
        "--dist-dir",
        type=Path,
        default=PROJECT_ROOT / "dist-sidecar",
        help="Build output directory (default: dist-sidecar)"
    )
    
    parser.add_argument(
        "--target-dir",
        type=Path,
        default=Path(os.environ.get("LOCALAPPDATA", "")) / "ZARA3" / "bin",
        help="Deployment target directory"
    )
    
    parser.add_argument(
        "--staging-dir",
        type=Path,
        help="Staging directory (default: target_dir/../staging)"
    )
    
    parser.add_argument(
        "--artifact",
        default="zara-backend.exe",
        help="Artifact name to deploy (default: zara-backend.exe)"
    )
    
    # Operation modes
    parser.add_argument(
        "--stage-only",
        action="store_true",
        help="Only stage artifact, do not deploy"
    )
    
    parser.add_argument(
        "--deploy-only",
        action="store_true",
        help="Deploy already staged artifact"
    )
    
    parser.add_argument(
        "--rollback",
        action="store_true",
        help="Rollback to previous backup"
    )
    
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip backup of existing artifact"
    )
    
    return parser


def main(args: list = None) -> int:
    """Main entry point."""
    parser = setup_parser()
    parsed_args = parser.parse_args(args)
    
    if parsed_args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled")
    
    # Validate mutually exclusive operations
    ops = sum([parsed_args.stage_only, parsed_args.deploy_only, parsed_args.rollback])
    if ops > 1:
        logger.error("Cannot combine --stage-only, --deploy-only, and --rollback")
        return 2
    
    # Validate target directory
    if not parsed_args.target_dir or str(parsed_args.target_dir).strip() == "":
        logger.error("Target directory not set. Use --target-dir or set LOCALAPPDATA")
        return 2
    
    manager = DeployManager(
        dist_dir=parsed_args.dist_dir,
        target_dir=parsed_args.target_dir,
        staging_dir=parsed_args.staging_dir
    )
    
    try:
        if parsed_args.rollback:
            result = manager.rollback()
            if result["success"]:
                logger.info("Rollback completed")
                return 0
            else:
                logger.error(f"Rollback failed: {result['error']}")
                return 1
        
        elif parsed_args.deploy_only:
            result = manager.deploy_staged(backup=not parsed_args.no_backup)
            if result["success"]:
                logger.info("Deployment completed")
                return 0
            else:
                logger.error(f"Deployment failed: {result['error']}")
                return 1
        
        elif parsed_args.stage_only:
            result = manager.stage_artifact(parsed_args.artifact)
            if result["success"]:
                logger.info("Staging completed")
                return 0
            else:
                logger.error(f"Staging failed: {result['error']}")
                return 1
        
        else:
            # Full deploy: stage + deploy
            result = manager.stage_artifact(parsed_args.artifact)
            if not result["success"]:
                logger.error(f"Staging failed: {result['error']}")
                return 1
            
            result = manager.deploy_staged(backup=not parsed_args.no_backup)
            if result["success"]:
                logger.info("Full deployment completed")
                return 0
            else:
                logger.error(f"Deployment failed: {result['error']}")
                return 1
                
    except KeyboardInterrupt:
        logger.warning("Deployment interrupted by user")
        return 130
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())