"""
Parser for hierarchy blocks using existing forge.core.creator functionality.
"""

from typing import Any

from pydantic import BaseModel, Field

from cancelable.utils.logging import get_logger

from .base import BlockParser

logger = get_logger(__name__)


class HierarchyContent(BaseModel):
    """Parsed content of hierarchy block."""

    raw_tree: str = Field(..., description="Raw tree representation")
    lines: list[str] = Field(default_factory=list, description="Individual lines")
    file_count: int = Field(default=0, description="Number of files")
    folder_count: int = Field(default=0, description="Number of folders")
    max_depth: int = Field(default=0, description="Maximum tree depth")
    # node_tree field removed - was specific to forge
    hierarchy_count: int = Field(default=1, description="Number of hierarchies found")


class HierarchyParser(BlockParser):
    """Parser for hierarchy blocks."""

    block_type: str = "hierarchy"
    description: str = "File/folder hierarchy trees"

    def parse_preamble(self, header: str) -> dict[str, Any]:
        """Parse hierarchy preamble."""
        return {"type": "hierarchy", "parameters": {}}

    def parse_content(self, content: str) -> HierarchyContent:
        """Parse hierarchy content."""
        lines = [line for line in content.split("\n") if line.strip()]

        # Basic parsing
        file_count = 0
        folder_count = 0
        max_depth = 0

        for i, line in enumerate(lines):
            # Count depth based on indentation
            stripped = line.lstrip()
            indent_level = (len(line) - len(stripped)) // 2  # Assuming 2-space indent
            if "│" in line or "├" in line or "└" in line:
                # Tree-style formatting
                indent_level = line.count("│")

            max_depth = max(max_depth, indent_level)

            # Remove tree characters
            cleaned = stripped.replace("├──", "").replace("└──", "").replace("│", "").strip()
            cleaned = cleaned.replace("├─", "").replace("└─", "").strip()  # Handle shorter variants

            # Skip the first line if it's a root folder (no tree characters)
            if i == 0 and "├" not in line and "└" not in line and "│" not in line and cleaned.endswith("/"):
                # This is a root folder label, don't count it
                continue

            if cleaned.endswith("/"):
                folder_count += 1
            elif cleaned and not cleaned.startswith("─"):
                file_count += 1

        return HierarchyContent(
            raw_tree=content,
            lines=lines,
            file_count=file_count,
            folder_count=folder_count,
            max_depth=max_depth,
            hierarchy_count=1
        )

    def format_block(self, block) -> None:
        """Custom formatting for hierarchy blocks."""
        print(f"\n{'-' * 30}")
        print(f"📁 FILE HIERARCHY (Block: {block.hash_id})")
        print(f"{'-' * 30}")
        print(f"📊 Stats: {block.content.file_count} files, {block.content.folder_count} folders")
        print(f"📏 Max depth: {block.content.max_depth} levels")

        if block.content.hierarchy_count > 1:
            print(f"📌 Found {block.content.hierarchy_count} hierarchies")

        print("\n📂 Structure:")
        print("┌" + "─" * 58 + "┐")

        lines = block.content.lines
        for line in lines[:15]:
            print(f"│ {line:<56} │")
        if len(lines) > 15:
            print(f"│ {'... and ' + str(len(lines) - 15) + ' more lines':<56} │")

        print("└" + "─" * 58 + "┘")

    def validate_block(self, block) -> str | None:
        """Validate the hierarchy block."""
        if block.content.file_count == 0 and block.content.folder_count == 0:
            return "No valid hierarchy structure found"
        return None
