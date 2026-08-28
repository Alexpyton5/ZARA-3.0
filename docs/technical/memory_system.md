# Memory System in ZARA 3.0

## Overview

ZARA 3.0 features a sophisticated memory system called the "Cérebro do Alex" (Alex's Brain) that organizes knowledge into three independent compartments (gavetas): MEMORY, KNOWLEDGE, and SKILL. This design allows for flexible knowledge organization while maintaining isolation between different types of information.

## Three Compartments (Gavetas)

The memory system separates knowledge into three distinct compartments:

1. **MEMORY** - Personal facts, decisions, preferences, identity, relationships, desires, and notes
2. **KNOWLEDGE** - Imported external content such as PDFs, videos, websites, and documents
3. **SKILL** - Procedures, how-to guides, skills, workflows, and learned workflows

Each compartment has:
- Its own directory in `%LOCALAPPDATA%\ZARA3\data\brain\vault\<gaveta>\notes\`
- Isolated SQLite tables: `<gaveta>_documents`, `<gaveta>_provenance`, `<gaveta>_fts`
- Independent FTS5 search capability that can be scoped to a single compartment or searched across all compartments

## Storage Architecture

The system uses a hybrid approach:
- **Markdown files** as the canonical, human-readable data format
- **SQLite database** as a derived search index with FTS5 (Full-Text Search) and vector storage capabilities
- The SQLite index can be rebuilt at any time from the Markdown source files
- Imports copy safe notes without modifying or removing source vaults

## Key Components

### BrainStore Class
The main interface to the memory system is the `BrainStore` class in `brain/store.py` which provides:
- Vault importing with duplicate detection and secret blocking
- Compartment-based organization
- Provenance tracking (source attribution)
- SHA-256 hashing for content addressing
- Embedding generation for semantic search (via Ollama's nomic-embed-text model)

### Memory Operations
- **Import**: Copy safe Markdown notes into the canonical vault with provenance tracking
- **Search**: FTS5-based text search with optional vector similarity search
- **Citation**: Track source information including SHA-256 hashes for verification
- **Compartmentalization**: Automatic or manual assignment of content to appropriate gavetas

## Technical Details

### Storage Locations
- Vault root: `%LOCALAPPDATA%\ZARA3\data\brain\`
- Compartment directories: `vault\<gaveta>\notes\` for each gaveta
- Database: `brain.db` (SQLite with FTS5 and vector storage)
- Manifest: `manifest.json` (tracks import history and schema version)

### Search Capabilities
- Text search via FTS5 with unicode61 tokenizer and diacritic removal
- Vector similarity search using embeddings (when Ollama is available)
- Cross-compartment or scoped-to-single-compartment search
- Provenance tracking for all imported content

### Security Features
- Automatic detection and blocking of likely credentials/keys during import
- SHA-256 hashing for content integrity
- Path traversal protection during file operations
- Secret pattern matching for common credential formats

## Status

**PRONTO** — Functional and tested as part of Fases 1-2. The three gavetas system (brain/store.py, brain/migrate_legacy.py) successfully separates memory, knowledge, and skills without losing search capability.