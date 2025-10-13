"""
Parser for file patch blocks.
"""

import re
from typing import Any

from pydantic import BaseModel, Field

from hother.cancelable.utils.logging import get_logger

from .base import BlockParser

logger = get_logger(__name__)


class FilePatchContent(BaseModel):
    """Parsed content of file patch block."""

    reference_line: str | None = Field(None, description="Reference line content (first line to replace/insert after/delete from)")
    code: str | None = Field(None, description="Code content for patch")
    language: str | None = Field(None, description="Code language")
    reference_language: str | None = Field(None, description="Reference line language")
    has_code: bool = Field(False, description="Whether code was provided")
    has_reference: bool = Field(False, description="Whether reference line was provided")


class FilePatchParser(BlockParser):
    """Parser for file patch blocks."""

    block_type: str = "file_patch"
    description: str = "File patches with operations R/I/D"

    def parse_preamble(self, header: str) -> dict[str, Any]:
        """
        Parse file patch preamble.
        Format: <file_path>:Op<lines>
        """
        # Find the last colon to separate file path from operation
        last_colon = header.rfind(":")
        if last_colon == -1:
            return {"type": "file_patch", "parameters": {"error": "Invalid format"}}

        file_path = header[:last_colon].strip()
        op_and_lines = header[last_colon + 1 :].strip()

        # Parse operation and lines
        if not op_and_lines:
            return {"type": "file_patch", "parameters": {"error": "Missing operation"}}

        operation = op_and_lines[0].upper()
        if operation not in ["R", "I", "D"]:
            return {"type": "file_patch", "parameters": {"error": f"Invalid operation: {operation}"}}

        lines_str = op_and_lines[1:]

        # Parse line specification
        line_start = None
        line_end = None
        insert_after = False

        try:
            if "+" in lines_str:
                # Insert after format: 5+
                line_start = int(lines_str.replace("+", ""))
                insert_after = True
            elif "-" in lines_str:
                # Range format: 5-7
                parts = lines_str.split("-")
                if len(parts) == 2:
                    line_start = int(parts[0])
                    line_end = int(parts[1])
            else:
                # Single line: 5
                line_start = int(lines_str)
                line_end = line_start
        except ValueError:
            return {"type": "file_patch", "parameters": {"error": f"Invalid line specification: {lines_str}"}}

        return {"type": "file_patch", "parameters": {"file_path": file_path, "operation": operation, "line_start": line_start, "line_end": line_end, "insert_after": insert_after}}

    def parse_content(self, content: str) -> FilePatchContent:
        """
        Parse file patch content.
        Extracts two code blocks: first for reference line, second for the actual code.
        """
        # For delete operations, there might be no content
        if not content.strip():
            return FilePatchContent()

        # Look for all code blocks with triple backticks
        code_pattern = r"```(\w*)\n(.*?)\n```"
        matches = list(re.finditer(code_pattern, content, re.DOTALL))

        if len(matches) >= 2:
            # First block is the reference line
            reference_match = matches[0]
            reference_language = reference_match.group(1) or "text"
            reference_line = reference_match.group(2).strip()

            # Second block is the actual code
            code_match = matches[1]
            code_language = code_match.group(1) or "text"
            code = code_match.group(2)

            return FilePatchContent(
                reference_line=reference_line.splitlines(keepends=True)[0],
                code=code,
                language=code_language,
                reference_language=reference_language,
                has_code=True,
                has_reference=True
            )
        if len(matches) == 1:
            # Only one code block found - treat as reference line for delete operations
            # or as code for insert/replace operations
            match = matches[0]
            language = match.group(1) or "text"
            code_content = match.group(2)

            # If it's a single line, treat it as reference line
            if len(code_content.strip().split('\n')) == 1:
                return FilePatchContent(
                    reference_line=code_content.splitlines(keepends=True)[0],
                    reference_language=language,
                    has_reference=True
                )
            # Multiple lines, treat as code
            return FilePatchContent(
                code=code_content,
                language=language,
                has_code=True
            )
        # No code blocks found - treat entire content as reference if it's a single line
        content_stripped = content.strip()
        if content_stripped and len(content_stripped.split('\n')) == 1:
            return FilePatchContent(
                reference_line=content_stripped,
                reference_language="text",
                has_reference=True
            )
        if content_stripped:
            return FilePatchContent(
                code=content_stripped,
                language="text",
                has_code=True
            )

        return FilePatchContent()

    def format_block(self, block) -> None:
        """Custom formatting for file patch blocks."""
        print(f"\n{'-' * 30}")
        print(f"📝 FILE PATCH (Block: {block.hash_id})")
        print(f"{'-' * 30}")

        params = block.parameters
        file_path = params.get("file_path", "unknown")
        operation = params.get("operation", "?")
        line_start = params.get("line_start")
        line_end = params.get("line_end")
        insert_after = params.get("insert_after", False)

        # Show file and operation
        print(f"📄 File: {file_path}")

        # Describe the operation
        if operation == "R":
            if line_start == line_end:
                print(f"🔄 Operation: REPLACE line {line_start}")
            else:
                print(f"🔄 Operation: REPLACE lines {line_start}-{line_end}")
        elif operation == "I":
            if insert_after:
                print(f"➕ Operation: INSERT after line {line_start}")
            else:
                print(f"➕ Operation: INSERT at line {line_start}")
        elif operation == "D":
            if line_start == line_end:
                print(f"❌ Operation: DELETE line {line_start}")
            else:
                print(f"❌ Operation: DELETE lines {line_start}-{line_end}")

        # Show reference line if present
        if block.content.has_reference and block.content.reference_line:
            ref_language = block.content.reference_language or "text"
            print(f"\n🎯 Reference Line ({ref_language}):")
            print("┌" + "─" * 58 + "┐")
            ref_line = block.content.reference_line
            if len(ref_line) > 54:
                ref_line = ref_line[:51] + "..."
            print(f"│ {ref_line:<56} │")
            print("└" + "─" * 58 + "┘")

        # Show code if present
        if block.content.has_code and block.content.code:
            code = block.content.code
            language = block.content.language or "text"

            print(f"\n📋 New Code ({language}):")
            print("┌" + "─" * 58 + "┐")

            # Show code with line numbers
            lines = code.split("\n")
            for i, line in enumerate(lines[:20], 1):  # Show up to 20 lines
                # Truncate long lines
                if len(line) > 56:
                    line = line[:53] + "..."
                print(f"│ {i:2d} {line:<54} │")

            if len(lines) > 20:
                print(f"│ {'... ' + str(len(lines) - 20) + ' more lines':<56} │")

            print("└" + "─" * 58 + "┘")
        elif operation != "D" and not block.content.has_reference:
            print("\n⚠️  No code provided for replace/insert operation")
