"""
Parser for action blocks with dependencies and parameters.
"""

import re
from typing import Any

from pydantic import BaseModel, Field

from hother.cancelable.utils.logging import get_logger

from .base import BlockParser

logger = get_logger(__name__)


class ActionReference(BaseModel):
    """Reference to another action's output."""

    ref: str = Field(..., description="Reference to action ID")
    path: str | None = Field(None, description="JSON path to specific value")
    default_value: str | None = Field(None, description="Default if reference fails")


class ActionContent(BaseModel):
    """Parsed content of an action block."""

    parameters: dict[str, Any] = Field(default_factory=dict, description="Direct parameters")
    references: dict[str, ActionReference] = Field(default_factory=dict, description="Parameter references")
    raw_text: str | None = Field(None, description="Any non-parameter text")


class ActionParser(BlockParser):
    """Parser for action blocks."""

    block_type: str = "a"
    description: str = "Action blocks with dependencies and XML-style parameters"

    def parse_preamble(self, header: str) -> dict[str, Any]:
        """
        Parse action preamble.
        Format: action_name:after(id_1, id_2, ...)
        """
        # Check if there's an 'after' clause
        after_match = re.match(r"([^:]+):after\(([^)]*)\)", header)
        if after_match:
            action_name = after_match.group(1).strip()
            dependencies_str = after_match.group(2).strip()
            dependencies = [dep.strip() for dep in dependencies_str.split(",") if dep.strip()]

            return {"type": "action", "parameters": {"action_name": action_name, "dependencies": dependencies}}

        # No after clause - just action name
        action_name = header.strip()
        return {"type": "action", "parameters": {"action_name": action_name if action_name else "unnamed", "dependencies": []}}

    def parse_content(self, content: str) -> ActionContent:
        """
        Parse action content with XML-like parameter tags.
        """
        parameters = {}
        references = {}

        # Find all parameter tags
        param_pattern = r'<(\w+)(?:\s+ref="([^"]+)")?(?:\s+path="([^"]+)")?>([^<]*)</\1>'
        matches = re.findall(param_pattern, content, re.DOTALL)

        for match in matches:
            param_name = match[0]
            ref_value = match[1] if match[1] else None
            path_value = match[2] if match[2] else None
            param_value = match[3].strip()

            if ref_value:
                # This parameter references another action
                references[param_name] = ActionReference(ref=ref_value, path=path_value, default_value=param_value if param_value else None)
            else:
                # Regular parameter
                parameters[param_name] = param_value

        # Extract any non-XML content as raw text
        raw_text = re.sub(param_pattern, "", content).strip()

        return ActionContent(parameters=parameters, references=references, raw_text=raw_text if raw_text else None)

    def format_block(self, block) -> None:
        """Custom formatting for action blocks."""
        print(f"\n{'-' * 30}")
        print(f"🚀 ACTION: {block.parameters.get('action_name', 'Unnamed')} (Block: {block.hash_id})")
        print(f"{'-' * 30}")

        # Show dependencies
        dependencies = block.parameters.get("dependencies", [])
        if dependencies:
            print(f"⏳ Dependencies: Must wait for {', '.join(dependencies)}")
        else:
            print("⏳ Dependencies: None (can start immediately)")

        # Show parameters
        if block.content.parameters:
            print("\n📝 Parameters:")
            for name, value in block.content.parameters.items():
                display_value = value if len(str(value)) <= 50 else str(value)[:47] + "..."
                print(f"   • {name}: {display_value}")

        # Show references
        if block.content.references:
            print("\n🔗 Parameter References:")
            for param_name, ref_info in block.content.references.items():
                print(f"   • {param_name} → {ref_info.ref} (path: {ref_info.path or 'root'})")

        # Show raw text if any
        if block.content.raw_text:
            print("\n📄 Additional content:")
            print(f"   {block.content.raw_text[:100]}..." if len(block.content.raw_text) > 100 else f"   {block.content.raw_text}")
