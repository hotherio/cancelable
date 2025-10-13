"""
Parser for instruction blocks.
"""

import re
from typing import Any

from pydantic import BaseModel, Field

from .base import BlockParser


class InstructionContent(BaseModel):
    """Parsed content of instruction block."""

    instruction_text: str = Field(..., description="Full instruction text")
    steps: list[str] = Field(default_factory=list, description="Individual steps")
    step_count: int = Field(default=0, description="Number of steps")


class InstructionParser(BlockParser):
    """Parser for instruction blocks."""

    block_type: str = "instruction"
    description: str = "Step-by-step instructions"

    def parse_preamble(self, header: str) -> dict[str, Any]:
        """Parse instruction preamble."""
        param_match = re.match(r"instruction\(([^)]*)\)", header)
        if param_match:
            params_str = param_match.group(1)
            params = [p.strip() for p in params_str.split(",") if p.strip()]
            return {"type": "instruction", "parameters": {"instruction_params": params}}
        return {"type": "instruction", "parameters": {}}

    def parse_content(self, content: str) -> InstructionContent:
        """Parse instruction content."""
        lines = [line.strip() for line in content.split("\n") if line.strip()]
        return InstructionContent(instruction_text=content, steps=lines, step_count=len(lines))

    def format_block(self, block) -> None:
        """Custom formatting for instruction blocks."""
        print(f"\n{'-' * 30}")
        print(f"📚 INSTRUCTIONS (Block: {block.hash_id})")
        print(f"{'-' * 30}")

        params = block.parameters.get("instruction_params", [])
        if params:
            print(f"📌 Sections: {', '.join(params)}")

        print(f"📝 Total steps: {block.content.step_count}")
        print("\n🔢 Steps:")

        # Group steps by sections if they start with section names
        step_num = 1
        for step in block.content.steps:
            # Check if this step is a section header
            is_section = any(step.lower().startswith(p.lower() + ":") or step.lower().startswith(p.lower() + " instructions:") for p in params) if params else False

            if is_section:
                print(f"\n  ▶️  {step}")
                step_num = 1
            else:
                print(f"     {step_num}. {step}")
                step_num += 1
