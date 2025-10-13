"""
Block type registry system.
"""


from pydantic import BaseModel, ConfigDict, Field

from hother.cancelable.utils.logging import get_logger

from .parsers.base import BlockParser

logger = get_logger(__name__)


class BlockRegistry(BaseModel):
    """Registry for block types and their parsers."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    parsers: dict[str, BlockParser] = Field(default_factory=dict, description="Registered block parsers")

    def register(self, parser: BlockParser) -> None:
        """
        Register a block parser.

        Args:
            parser: The parser to register
        """
        if parser.block_type in self.parsers:
            logger.warning(f"Overwriting existing parser for block type: {parser.block_type}")
        self.parsers[parser.block_type] = parser
        logger.info(f"Registered parser for block type: {parser.block_type}")

    def get_parser(self, block_type: str) -> BlockParser | None:
        """
        Get parser for a block type.

        Args:
            block_type: The block type to look up

        Returns:
            Parser if found, None otherwise
        """
        return self.parsers.get(block_type)

    def list_types(self) -> list[str]:
        """Get list of registered block types."""
        return sorted(self.parsers.keys())

    @classmethod
    def create_default(cls) -> "BlockRegistry":
        """Create registry with default parsers."""
        from .parsers import (
            ActionParser,
            ComplexParser,
            FileOperationsParser,
            FilePatchParser,
            HierarchyParser,
            InstructionParser,
            SimpleParser,
        )

        registry = cls()

        # Register all default parsers
        registry.register(ActionParser())
        registry.register(FileOperationsParser())
        registry.register(FilePatchParser())
        registry.register(HierarchyParser())
        registry.register(InstructionParser())
        registry.register(SimpleParser())
        registry.register(ComplexParser())

        return registry
