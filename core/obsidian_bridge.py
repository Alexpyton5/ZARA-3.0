"""ObsidianBridge — bridge to local Obsidian-compatible vault for Galaxy memory graph."""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from typing import Any

from core.storage import safe_user_path


class ObsidianBridge:
    """
    Bridges ZARA to a local Obsidian-compatible vault.
    Provides galaxy() method returning nodes/links for the Galaxy view.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self.vault_path = safe_user_path("vault")
        self._index_file = self.vault_path / ".zara_index.json"
        self._ensure_vault()

    def _ensure_vault(self):
        """Create vault structure if not exists."""
        self.vault_path.mkdir(parents=True, exist_ok=True)
        (self.vault_path / "memories").mkdir(exist_ok=True)
        (self.vault_path / "knowledge").mkdir(exist_ok=True)
        (self.vault_path / "projects").mkdir(exist_ok=True)

        if not self._index_file.exists():
            self._save_index({"nodes": [], "links": []})

    def _load_index(self) -> dict[str, Any]:
        try:
            with open(self._index_file, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"nodes": [], "links": []}

    def _save_index(self, data: dict[str, Any]):
        from core.storage import atomic_write_json
        atomic_write_json(self._index_file, data)

    def galaxy(self) -> dict[str, Any]:
        """
        Returns the memory graph for Galaxy view.
        Format: {"nodes": [...], "links": [...]}
        """
        index = self._load_index()
        return {
            "nodes": index.get("nodes", []),
            "links": index.get("links", []),
        }

    def add_memory(self, title: str, content: str, tags: list[str] = None, category: str = "memories") -> str:
        """Add a new memory node to the vault."""
        node_id = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()

        # Save markdown file
        category_dir = self.vault_path / category
        category_dir.mkdir(exist_ok=True)
        md_path = category_dir / f"{node_id}-{title.replace(' ', '-')}.md"

        frontmatter = f"---\nid: {node_id}\ntitle: {title}\ntags: {tags or []}\ncreated: {now}\n---\n\n"
        md_path.write_text(frontmatter + content, encoding="utf-8")

        # Update index
        index = self._load_index()
        index["nodes"].append({
            "id": node_id,
            "title": title,
            "category": category,
            "tags": tags or [],
            "created": now,
            "path": str(md_path.relative_to(self.vault_path)),
        })
        self._save_index(index)

        return node_id

    def link_memories(self, source_id: str, target_id: str, relation: str = "relates_to"):
        """Create a link between two memories."""
        index = self._load_index()
        index["links"].append({
            "source": source_id,
            "target": target_id,
            "relation": relation,
        })
        self._save_index(index)


# Global instance
_bridge_instance = None


def get_bridge() -> ObsidianBridge:
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = ObsidianBridge()
    return _bridge_instance
