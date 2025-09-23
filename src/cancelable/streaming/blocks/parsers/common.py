"""
Parsers for simple and complex block types.
"""

import re
from typing import Any

from pydantic import BaseModel, Field

from .base import BlockParser


class ComplexContent(BaseModel):
    """Parsed content of complex block."""

    sections: dict[str, str] = Field(default_factory=dict, description="Named sections")
    section_count: int = Field(default=0, description="Number of sections")
    raw_content: str = Field(..., description="Raw content")


class SimpleParser(BlockParser):
    """Parser for simple blocks."""

    block_type: str = "simple"
    description: str = "Simple text blocks"

    def parse_preamble(self, header: str) -> dict[str, Any]:
        """Parse simple preamble."""
        return {"type": "simple", "parameters": {}}

    def parse_content(self, content: str) -> str:
        """Parse simple content."""
        return content.strip()

    def format_block(self, block) -> None:
        """Custom formatting for simple blocks."""
        print(f"\n{'-' * 20}")
        print(f"📄 SIMPLE BLOCK (Block: {block.hash_id})")
        print(f"{'-' * 20}")
        print("Content:")
        print("─" * 40)

        # Pretty print with word wrapping
        content = block.content if isinstance(block.content, str) else str(block.content)
        words = content.split()
        line = ""
        for word in words:
            if len(line) + len(word) + 1 > 60:
                print(line)
                line = word
            else:
                line = line + " " + word if line else word
        if line:
            print(line)
        print("─" * 40)


class ComplexParser(BlockParser):
    """Parser for complex blocks."""

    block_type: str = "complex"
    description: str = "Complex blocks with sections"

    def parse_preamble(self, header: str) -> dict[str, Any]:
        """Parse complex preamble with optional parameters."""
        if "(" in header and ")" in header:
            match = re.match(r"complex\(([^)]*)\)", header)
            if match:
                params = [p.strip() for p in match.group(1).split(",") if p.strip()]
                return {"type": "complex", "parameters": {"params": params}}

        parts = header.split(":")
        if len(parts) > 1 and parts[0] == "complex":
            return {"type": "complex", "parameters": {"colon_params": parts[1:]}}

        return {"type": "complex", "parameters": {}}

    def parse_content(self, content: str) -> ComplexContent:
        """Parse complex content with sections."""
        sections = {}
        current_section = None
        current_content = []

        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("---") and line.endswith("---"):
                if current_section:
                    sections[current_section] = "\n".join(current_content)
                current_section = line.strip("-").strip()
                current_content = []
            elif current_section:
                current_content.append(line)

        if current_section:
            sections[current_section] = "\n".join(current_content)

        return ComplexContent(sections=sections, section_count=len(sections), raw_content=content)

    def format_block(self, block) -> None:
        """Custom formatting for complex blocks."""
        print(f"\n{'🔧' * 25}")
        print(f"⚙️  COMPLEX BLOCK (Block: {block.hash_id})")
        print(f"{'🔧' * 25}")

        params = block.parameters.get("params", [])
        if params:
            print(f"Parameters: {', '.join(params)}")

        print(f"Sections: {block.content.section_count}")

        for section, content in block.content.sections.items():
            print(f"\n📌 {section}:")
            print("─" * 40)
            preview = content[:150].replace("\n", " ")
            if len(content) > 150:
                preview += "..."
            print(preview)
