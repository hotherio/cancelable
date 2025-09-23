"""
Core models for the block extraction system.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from cancelable.utils.logging import get_logger

logger = get_logger(__name__)


class BlockExtractionStatus(str, Enum):
    """Status of block extraction process."""

    SCANNING = "scanning"
    IN_BLOCK = "in_block"
    COMPLETED = "completed"
    ERROR = "error"


class ExtractedBlock(BaseModel):
    """A block that has been extracted from the stream."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    hash_id: str = Field(..., description="hash identifier")
    block_type: str = Field(..., description="Type of the block")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Parsed parameters from preamble")
    content: Any = Field(..., description="Parsed content of the block")
    raw_content: str = Field(..., description="Raw unparsed content")

    def __str__(self) -> str:
        """String representation."""
        return f"Block[{self.hash_id}:{self.block_type}]"

    def log_context(self) -> dict[str, Any]:
        """Get context dict for structured logging."""
        return {
            "block_id": self.hash_id,
            "block_type": self.block_type,
            "content_length": len(self.raw_content),
            "has_parameters": bool(self.parameters),
        }


class BlockExtractionState(BaseModel):
    """State for block extraction during streaming."""

    model_config = ConfigDict(validate_assignment=True)

    line_buffer: str = Field(default="", description="Buffer for incomplete lines")
    current_block_hash: str | None = Field(default=None, description="Hash of current block being processed")
    current_block_header: str | None = Field(default=None, description="Header of current block")
    current_block_lines: list[str] = Field(default_factory=list, description="Lines of current block")
    extracted_blocks: list[ExtractedBlock] = Field(default_factory=list, description="All extracted blocks")
    processed_lines: int = Field(default=0, ge=0, description="Number of lines processed")
    discarded_lines: int = Field(default=0, ge=0, description="Number of lines discarded")

    @property
    def status(self) -> BlockExtractionStatus:
        """Get current extraction status."""
        if self.current_block_hash is not None:
            return BlockExtractionStatus.IN_BLOCK
        if self.processed_lines > 0:
            return BlockExtractionStatus.SCANNING
        return BlockExtractionStatus.COMPLETED

    @property
    def current_state_description(self) -> str:
        """Get human-readable state description."""
        if self.current_block_hash is None:
            return "scanning_for_blocks"
        return f"in_block_{self.current_block_hash}_{len(self.current_block_lines)}_lines"

    def reset_current_block(self) -> None:
        """Reset current block state."""
        self.current_block_hash = None
        self.current_block_header = None
        self.current_block_lines = []


class BlockExtractionMetadata(BaseModel):
    """Metadata for block extraction events."""

    timestamp: float
    event_number: int
    event_type: str

    # Block extraction specific
    extraction_event_type: str = Field(description="Type of extraction event: chunk, block_extracted, etc.")
    line_buffer_size: int = Field(default=0, ge=0)
    current_state: str = Field(default="scanning")
    processed_lines: int = Field(default=0, ge=0)
    discarded_lines: int = Field(default=0, ge=0)
    total_blocks_extracted: int = Field(default=0, ge=0)

    # Optional fields for different event types
    chunk_data: str | None = None
    extracted_block: ExtractedBlock | None = None
    remaining_content: str | None = None

    def log_context(self) -> dict[str, Any]:
        """Get context dict for structured logging."""
        context = {
            "event_type": self.event_type,
            "extraction_event_type": self.extraction_event_type,
            "state": self.current_state,
            "processed_lines": self.processed_lines,
            "total_blocks": self.total_blocks_extracted,
        }
        if self.extracted_block:
            context.update(self.extracted_block.log_context())
        return context
