#!/usr/bin/env python3
"""
ZARA 3.0 — Unified CLI (Codex Patterns)
Main entry point for all ZARA automation commands.
"""

import argparse
import logging
import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Import sub-commands
from scripts.build import main as build_main
from scripts.deploy import main as deploy_main
from scripts.sync import main as sync_main
from scripts.health_check import main as health_main

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


class ZaraCLI:
    """Unified CLI for ZARA automation."""
    
    def __init__(self):
        self.commands = {
            "build": {
                "func": build_main,
                "help": "Build sidecar executable (zara-backend.exe)",
                "description": "Wrapper for build_exe.py with proper CLI interface"
            },
            "deploy": {
                "func": deploy_main,
                "help": "Deploy built artifacts with verification",
                "description": "Stage, verify, and deploy with rollback support"
            },
            "sync": {
                "func": sync_main,
                "help": "Sync configurations, data, and state",
                "description": "Bidirectional sync between project and runtime directories"
            },
            "health": {
                "func": health_main,
                "help": "Comprehensive health verification",
                "description": "Check Python env, dependencies, directories, build artifacts, and more"
            },
        }
    
    def create_parser(self) -> argparse.ArgumentParser:
        """Create main parser with subcommands."""
        parser = argparse.ArgumentParser(
            prog="zara",
            description="ZARA 3.0 — Neural Interface Automation CLI",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog=f"""
Available commands:
  build     Build sidecar executable (zara-backend.exe)
  deploy    Deploy built artifacts with verification and rollback
  sync      Sync configurations, data, and state between environments
  health    Comprehensive health verification

Run 'zara <command> --help' for command-specific options.

Examples:
  zara build                    # Full build
  zara build --no-clean         # Incremental build
  zara deploy                   # Stage + deploy
  zara deploy --stage-only      # Only stage
  zara deploy --rollback        # Rollback to backup
  zara sync                     # Sync config + data
  zara sync --include-memory    # Include memory databases
  zara sync --reverse           # Pull from runtime to project
  zara health                   # Full health check
  zara health --no-build        # Skip build artifact check

Environment:
  ZARA3_HOME    Override data directory (for testing/parallel runtimes)
  LOCALAPPDATA  Windows default data directory
            """
        )
        
        parser.add_argument(
            "-v", "--verbose",
            action="store_true",
            help="Enable verbose (DEBUG) logging globally"
        )
        
        parser.add_argument(
            "--version",
            action="version",
            version="ZARA 3.0 CLI v1.0.0"
        )
        
        # Add subcommands
        subparsers = parser.add_subparsers(
            dest="command",
            title="commands",
            metavar="<command>",
            required=True
        )
        
        # Build subcommand
        build_parser = subparsers.add_parser(
            "build",
            help=self.commands["build"]["help"],
            description=self.commands["build"]["description"],
            formatter_class=argparse.RawDescriptionHelpFormatter
        )
        self._add_build_args(build_parser)
        
        # Deploy subcommand
        deploy_parser = subparsers.add_parser(
            "deploy",
            help=self.commands["deploy"]["help"],
            description=self.commands["deploy"]["description"],
            formatter_class=argparse.RawDescriptionHelpFormatter
        )
        self._add_deploy_args(deploy_parser)
        
        # Sync subcommand
        sync_parser = subparsers.add_parser(
            "sync",
            help=self.commands["sync"]["help"],
            description=self.commands["sync"]["description"],
            formatter_class=argparse.RawDescriptionHelpFormatter
        )
        self._add_sync_args(sync_parser)
        
        # Health subcommand
        health_parser = subparsers.add_parser(
            "health",
            help=self.commands["health"]["help"],
            description=self.commands["health"]["description"],
            formatter_class=argparse.RawDescriptionHelpFormatter
        )
        self._add_health_args(health_parser)
        
        return parser
    
    def _add_build_args(self, parser: argparse.ArgumentParser):
        """Add build-specific arguments."""
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
    
    def _add_deploy_args(self, parser: argparse.ArgumentParser):
        """Add deploy-specific arguments."""
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
    
    def _add_sync_args(self, parser: argparse.ArgumentParser):
        """Add sync-specific arguments."""
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
    
    def _add_health_args(self, parser: argparse.ArgumentParser):
        """Add health-specific arguments."""
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
    
    def run(self, args: list = None) -> int:
        """Run the CLI."""
        parser = self.create_parser()
        parsed = parser.parse_args(args)
        
        if parsed.verbose:
            logging.getLogger().setLevel(logging.DEBUG)
            logger.debug("Verbose logging enabled")
        
        # Route to appropriate subcommand
        command = parsed.command
        
        if command not in self.commands:
            logger.error(f"Unknown command: {command}")
            return 2
        
        # Build sys.argv for subcommand
        subcommand_args = []
        for key, value in vars(parsed).items():
            if key in ("command", "verbose", "version"):
                continue
            if isinstance(value, bool) and value:
                subcommand_args.append(f"--{key.replace('_', '-')}")
            elif value is not None and not isinstance(value, bool):
                subcommand_args.append(f"--{key.replace('_', '-')}")
                subcommand_args.append(str(value))
        
        # Execute subcommand
        try:
            return self.commands[command]["func"](subcommand_args)
        except SystemExit as e:
            return e.code
        except KeyboardInterrupt:
            logger.warning("Operation interrupted by user")
            return 130
        except Exception as e:
            logger.exception(f"Unexpected error: {e}")
            return 1


def main(args: list = None) -> int:
    """Main entry point."""
    cli = ZaraCLI()
    return cli.run(args)


if __name__ == "__main__":
    sys.exit(main())