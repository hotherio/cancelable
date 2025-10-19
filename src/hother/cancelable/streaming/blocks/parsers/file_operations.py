"""
Parser for file operations blocks.
"""

from typing import Any

from pydantic import BaseModel, Field

from hother.cancelable.utils.logging import get_logger

from .base import BlockParser

logger = get_logger(__name__)


class FileOperationsContent(BaseModel):
    """Parsed content of file operations block."""

    operations: dict[str, list[str]] = Field(default_factory=lambda: {"create": [], "delete": [], "edit": []}, description="Operations grouped by type")
    all_operations: list[tuple[str, str]] = Field(default_factory=list, description="Ordered list of (operation, path) tuples")
    total_operations: int = Field(default=0, description="Total number of operations")
    folders: list[str] = Field(default_factory=list, description="Affected folders")
    files: list[str] = Field(default_factory=list, description="Affected files")
    errors: list[str] = Field(default_factory=list, description="Parsing errors")


class FileOperationsParser(BlockParser):
    """Parser for file operations blocks."""

    block_type: str = "files_operations"
    description: str = "File operations with C/D/E format"

    def parse_preamble(self, header: str) -> dict[str, Any]:
        """Parse files_operations preamble."""
        return {"type": "files_operations", "parameters": {}}

    def parse_content(self, content: str) -> FileOperationsContent:
        """
        Parse files_operations content.
        Format: path:operation where operation is C/D/E
        """
        result = FileOperationsContent()

        for line_num, line in enumerate(content.split("\n"), 1):
            line = line.strip()
            if not line:
                continue

            if ":" not in line:
                result.errors.append(f"Line {line_num}: Invalid format (missing ':'): {line}")
                continue

            # Use rsplit to handle paths with colons
            parts = line.rsplit(":", 1)
            if len(parts) != 2:
                result.errors.append(f"Line {line_num}: Invalid format: {line}")
                continue

            path = parts[0].strip()
            operation = parts[1].strip().upper()

            if operation == "C":
                result.operations["create"].append(path)
                result.all_operations.append(("create", path))
            elif operation == "D":
                result.operations["delete"].append(path)
                result.all_operations.append(("delete", path))
            elif operation == "E":
                result.operations["edit"].append(path)
                result.all_operations.append(("edit", path))
            else:
                result.errors.append(f"Line {line_num}: Unknown operation '{operation}' for {path}")
                continue

        # Extract folder structure from paths
        folders_set = set()
        files_set = set()

        for op_type, path in result.all_operations:
            if op_type != "delete":  # Don't count deleted files
                parts = path.split("/")
                # Build folder paths
                for i in range(1, len(parts)):
                    folder_path = "/".join(parts[:i])
                    if folder_path:
                        folders_set.add(folder_path)
                # Add the file
                files_set.add(path)

        result.folders = sorted(list(folders_set))
        result.files = sorted(list(files_set))
        result.total_operations = len(result.all_operations)

        return result

    def format_block(self, block) -> None:
        """Custom formatting for file operations blocks."""
        logger.info(f"FILE OPERATIONS (Block: {block.hash_id})")

        content = block.content
        logger.info(f"Total operations: {content.total_operations}")

        ops = content.operations

        if ops["create"]:
            logger.info(f"CREATE ({len(ops['create'])} files):")
            for path in ops["create"][:10]:
                logger.info(f"  + {path}")
            if len(ops["create"]) > 10:
                logger.info(f"  ... and {len(ops['create']) - 10} more")

        if ops["edit"]:
            logger.info(f"EDIT ({len(ops['edit'])} files):")
            for path in ops["edit"][:10]:
                logger.info(f"  ~ {path}")
            if len(ops["edit"]) > 10:
                logger.info(f"  ... and {len(ops['edit']) - 10} more")

        if ops["delete"]:
            logger.info(f"DELETE ({len(ops['delete'])} files):")
            for path in ops["delete"][:10]:
                logger.info(f"  - {path}")
            if len(ops["delete"]) > 10:
                logger.info(f"  ... and {len(ops['delete']) - 10} more")

        # Show folder structure
        if content.folders:
            logger.info(f"Folders affected ({len(content.folders)}):")
            for folder in content.folders[:10]:
                depth = folder.count("/")
                indent = "  " * depth
                folder_name = folder.split("/")[-1] if "/" in folder else folder
                logger.info(f"  {indent}📁 {folder_name}/")
            if len(content.folders) > 10:
                logger.info(f"  ... and {len(content.folders) - 10} more folders")

        # Show errors if any
        if content.errors:
            logger.warning(f"ERRORS ({len(content.errors)}):")
            for error in content.errors:
                logger.warning(f"  {error}")
