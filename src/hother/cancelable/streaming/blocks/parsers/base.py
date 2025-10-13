"""
Base interfaces for block parsers.
"""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from hother.cancelable.utils.logging import get_logger

from ..models import ExtractedBlock

logger = get_logger(__name__)


class BlockParser(BaseModel, ABC):
    """Base class for all block parsers."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    block_type: str = Field(..., description="Type identifier for this block")
    description: str = Field(default="", description="Human-readable description")

    @abstractmethod
    def parse_preamble(self, header: str) -> dict[str, Any]:
        """
        Parse the block preamble/header.

        Args:
            header: The header string after the block type

        Returns:
            Dictionary with 'type' and 'parameters' keys
        """

    @abstractmethod
    def parse_content(self, content: str) -> Any:
        """
        Parse the block content.

        Args:
            content: The raw content between block start and end

        Returns:
            Parsed content in appropriate format
        """

    def format_block(self, block: ExtractedBlock) -> None:
        """
        Pretty print the block. Override for custom formatting.

        Args:
            block: The extracted block to format
        """
        print(f"\n{'=' * 60}")
        print(f"Block Type: {block.block_type}")
        print(f"Hash: {block.hash_id}")
        print(f"Parameters: {block.parameters}")
        print(f"{'-' * 60}")
        print("Content (raw):")
        print(block.raw_content)
        print(f"{'=' * 60}")

    def validate_block(self, block: ExtractedBlock) -> str | None:
        """
        Validate the block. Override for custom validation.

        Args:
            block: The extracted block to validate

        Returns:
            Error message if invalid, None if valid
        """
        return None
