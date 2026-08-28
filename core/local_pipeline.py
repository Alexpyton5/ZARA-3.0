"""Local Pipeline — Local voice/text processing pipeline (stub for imports)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class LocalPipelineResult:
    """Result of local pipeline processing."""
    success: bool
    text: str = ""
    intent: Optional[str] = None
    action: Optional[str] = None
    params: dict = None
    error: str = ""


class LocalPipeline:
    """Local processing pipeline (stub implementation)."""

    def __init__(self):
        self._initialized = False

    async def initialize(self):
        self._initialized = True

    async def process(self, text: str, context: dict = None) -> LocalPipelineResult:
        """Process text through local pipeline."""
        if not self._initialized:
            await self.initialize()

        # Stub: just return the text
        return LocalPipelineResult(
            success=True,
            text=text,
        )

    async def shutdown(self):
        self._initialized = False


# Global instance
local_pipeline = LocalPipeline()