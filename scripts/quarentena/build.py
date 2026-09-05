#!/usr/bin/env python3
"""
ZARA 3.0 — Build CLI (Codex Patterns)
Wrapper for build_exe.py with proper CLI interface, logging, and error handling.
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from build_exe import build, clean_sidecar_dirs, verify_build

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


def setup_parser() -> argparse.ArgumentParser:
    """Create and configure argument parser."""
    parser = argparse.ArgumentParser(
        prog="zara-build",
        description="ZARA 3.0 Sidecar Builder (zara-backend.exe)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  zara-build                  # Full build (clean + compile + verify)
  zara-build --no-clean       # Incremental build (skip clean)
  zara-build --verify-only    # Only verify existing build
  zara-build --clean-only     # Only clean build artifacts
  zara-build -v               # Verbose output
        """
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG) logging"
    )
    
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Skip clean step (incremental build)"
    )
    
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify existing build artifact"
    )
    
    parser.add_argument(
        "--clean-only",
        action="store_true",
        help="Only clean build artifacts, do not build"
    )
    
    parser.add_argument(
        "--dist-dir",
        type=Path,
        default=PROJECT_ROOT / "dist-sidecar",
        help="Output directory for built EXE (default: dist-sidecar)"
    )
    
    return parser


def run_verify_only(dist_dir: Path) -> int:
    """Run verification only."""
    logger.info("Running verification only...")
    
    if verify_build():
        logger.info("Verification PASSED")
        return 0
    else:
        logger.error("Verification FAILED")
        return 1


def run_clean_only() -> int:
    """Run clean only."""
    logger.info("Cleaning build artifacts...")
    clean_sidecar_dirs()
    logger.info("Clean completed")
    return 0


def run_full_build(skip_clean: bool, dist_dir: Path) -> int:
    """Run full build process."""
    if skip_clean:
        logger.info("Skipping clean step (incremental build)")
    else:
        logger.info("Cleaning previous build artifacts...")
        clean_sidecar_dirs()
    
    logger.info("Starting sidecar build...")
    result = build()
    
    if result == 0:
        logger.info("Build completed successfully")
    else:
        logger.error("Build failed")
    
    return result


def main(args: list = None) -> int:
    """Main entry point."""
    parser = setup_parser()
    parsed_args = parser.parse_args(args)
    
    if parsed_args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled")
    
    # Handle mutually exclusive operations
    operations = sum([
        parsed_args.verify_only,
        parsed_args.clean_only,
    ])
    
    if operations > 1:
        logger.error("Cannot combine --verify-only with --clean-only")
        return 2
    
    try:
        if parsed_args.verify_only:
            return run_verify_only(parsed_args.dist_dir)
        elif parsed_args.clean_only:
            return run_clean_only()
        else:
            return run_full_build(parsed_args.no_clean, parsed_args.dist_dir)
    except KeyboardInterrupt:
        logger.warning("Build interrupted by user")
        return 130
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())