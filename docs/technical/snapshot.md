# Snapshot System in ZARA 3.0

## Overview

The snapshot system in ZARA 3.0 allows creating a clean export of the operational data layer (the "cérebro") while excluding sensitive information, caches, and build artifacts. This is used for backups, migration, and sharing the agent's learned knowledge without exposing secrets.

## Purpose

- Export only the persistent data layer (MEMORY, CONFIG, DATA, LEMBRETES, SKILLS, INTEGRATIONS, IDENTITY, INITIATIVE, PERCEPTION, and specific CORE files like the Task Registry/LAB components)
- Automatically redact sensitive data such as API keys and tokens in `api_keys.json`
- Exclude cache directories (`__pycache__`, `*.pyc`) and build artifacts
- Prevent path traversal attacks during restore
- Provide a manifest describing the snapshot contents and creation time
- Support dry-run mode for safe testing

## Key Features

### Selective Export
The snapshot includes:
- Memory export (via `memory.memory_manager.export_memory`) with automatic redaction of sensitive values
- Configuration directory (with `api_keys.json` redacted, other files copied)
- User data directories: `data`, `lembretes`, `skills`, `integrations`
- Identity and persona: `core/identity`
- Initiatives (automations): `core/initiative`
- Perception module: `core/perception`
- Specific CORE files that are part of the Task Registry/LAB: `lab_coordinator.py`, `autonomy_lab_bridge.py`, `capability_registry.py`

### Security Measures
- Sensitive filenames are detected and excluded (except `api_keys.json` which is redacted rather than excluded)
- No fallback to copying the original file if redaction fails
- Path traversal protection: all paths are validated to ensure they stay within the target directory
- Manifest includes a note about the snapshot being the data layer only, with secret redaction

### Restore Process
- Can restore to a clean directory with optional dry-run mode
- Verifies that the target directory is safe before copying
- Reports any issues during restore

## Implementation

The snapshot functionality is implemented in `snapshot_zara.py` with the following main functions:
- `export_cerebro(snapshot_dir)`: Creates the snapshot
- `redact_api_keys_file(src, dst)`: Redsensitive keys in `api_keys.json`
- `copy_with_redaction(src, dst, redaction_fn)`: Copies a file applying redaction if provided
- `copytree_filtered(src, dst)`: Copies a directory tree while excluding sensitive files and caches
- `verify_export(snapshot_dir)`: Checks for obvious secret leaks in the exported snapshot
- `restore_snapshot(snapshot_dir, target_dir, dry_run=True)`: Restores from a snapshot
- `audit_existing_snapshots(snapshots_base, quarantine_dir)`: Audits existing snapshots and moves insecure ones to quarantine

## Usage

```bash
# Create a snapshot (dry-run first recommended)
python snapshot_zara.py --output /tmp/zara-snapshot

# Restore from snapshot (dry-run first)
python snapshot_zara.py --snapshot /tmp/zara-snapshot --restore /tmp/zara-restored
```

## Status

**PRONTO** — Functional and tested as part of Fases 1-2. The snapshot system successfully exports the data layer with secret redaction and excludes caches/builds.