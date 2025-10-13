"""Stream processing utilities for async operations."""

# Import from blocks submodule
from .blocks import (
    BlockExtractionMetadata,
    BlockExtractionState,
    BlockExtractionStatus,
    BlockParser,
    BlockRegistry,
    ExtractedBlock,
    process_stream_with_blocks,
)

# Import from processor
from .processor import (
    BlockMetadata,
    DefaultMetadata,
    ProcessedEvent,
    StreamMetadata,
    create_llm_metadata_extractor,
    process_stream,
)

# Import from config
from .simulator import StreamConfig

__all__ = [
    # Processor exports
    "process_stream",
    "ProcessedEvent",
    "DefaultMetadata",
    "StreamMetadata",
    "BlockMetadata",
    "create_llm_metadata_extractor",
    # Block extraction exports
    "ExtractedBlock",
    "BlockExtractionState",
    "BlockExtractionStatus",
    "BlockExtractionMetadata",
    "BlockRegistry",
    "BlockParser",
    "process_stream_with_blocks",
    # Config
    "StreamConfig",
]
