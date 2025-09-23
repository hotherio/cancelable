"""
Core block extraction logic for streaming data.
"""

import re
import time
from collections.abc import AsyncGenerator, Callable
from typing import Any

from cancelable import Cancellable
from cancelable.utils.logging import get_logger

from ..processor import ProcessedEvent, process_stream
from .models import BlockExtractionMetadata, BlockExtractionState, ExtractedBlock
from .registry import BlockRegistry

logger = get_logger(__name__)


class BlockExtractor:
    """Handles block extraction from streaming text."""

    def __init__(self, registry: BlockRegistry, debug: bool = False):
        """
        Initialize block extractor.

        Args:
            registry: Block registry with parsers
            debug: Enable debug logging
        """
        self.registry = registry
        self.debug = debug
        self.state = BlockExtractionState()

    def process_line(self, line: str) -> ExtractedBlock | None:
        """
        Process a single line and potentially extract a block.

        Args:
            line: Line to process

        Returns:
            Extracted block if one was completed, None otherwise
        """
        line = line.rstrip("\r")
        self.state.processed_lines += 1

        if self.debug:
            logger.debug(f"Processing line {self.state.processed_lines}: {repr(line[:50])}")

        # Check for block end
        end_match = re.match(r"!!(\w+):end", line.strip())
        #print('END MATCH', end_match, line)
        if end_match:
            hash_id = end_match.group(1)
            #print('>>>> ID END MATCH', hash_id)
            if self.state.current_block_hash == hash_id:
                # Complete the current block
                if self.state.current_block_header:
                    return self._complete_block()
            elif self.state.current_block_hash is not None:
                # End tag doesn't match - treat as content
                self.state.current_block_lines.append(line)
            else:
                # Orphaned end tag
                self.state.discarded_lines += 1
            return None

        # Check for block start
        start_match = re.match(r"!!(\w+):(.+)", line.strip())
        #print('START MATCH >>> ', start_match, line.strip())
        if start_match:
            hash_id, header = start_match.groups()
            #print('NEW MATCH', hash_id, header)
            header = header.strip()

            if header == "end":
                return None

            # If already in a block, treat as content
            if self.state.current_block_hash is not None:
                self.state.current_block_lines.append(line)
                return None

            # Start new block
            self.state.current_block_hash = hash_id
            self.state.current_block_header = header
            self.state.current_block_lines = []

            if self.debug:
                logger.debug(f"Started block {hash_id}:{header}")

            return None

        # Regular content line
        if self.state.current_block_hash is not None:
            self.state.current_block_lines.append(line)
        else:
            self.state.discarded_lines += 1

        return None

    def _complete_block(self) -> ExtractedBlock | None:
        """Complete the current block and return it."""
        if not self.state.current_block_hash or not self.state.current_block_header:
            return None

        hash_id = self.state.current_block_hash
        header = self.state.current_block_header
        content = "\n".join(self.state.current_block_lines)

        if self.debug:
            logger.debug(f"Completing block {hash_id}:{header} with {len(self.state.current_block_lines)} lines")

        # Reset state
        self.state.reset_current_block()

        # Parse block header to get type
        block_info = self._parse_block_header(header)
        if not block_info:
            return None

        block_type = block_info["type"]
        parser = self.registry.get_parser(block_type)

        if not parser:
            if self.debug:
                logger.debug(f"Unknown block type '{block_type}'")
            return None

        try:
            # Parse preamble with remaining header
            remaining_header = block_info.get("remaining_header", "")
            parsed_preamble = parser.parse_preamble(remaining_header)

            # Parse content
            parsed_content = parser.parse_content(content.strip())

            # Create extracted block
            block = ExtractedBlock(hash_id=hash_id, block_type=block_type, parameters=parsed_preamble.get("parameters", {}), content=parsed_content, raw_content=content.strip())

            # Validate if parser provides validation
            error = parser.validate_block(block)
            if error:
                logger.warning(f"Block validation failed: {error}")
                if self.debug:
                    return None

            return block

        except Exception as e:
            logger.error(f"Error parsing block {block_type}: {e}", block_type=block_type, hash_id=hash_id)
            if self.debug:
                logger.debug(f"Raw header: '{header}'")
                logger.debug(f"Raw content: '{content[:200]}...'")
            return None

    def _parse_block_header(self, header: str) -> dict[str, Any] | None:
        """Parse block header to extract type and remaining content."""
        header = header.rstrip(":").strip()

        # Extract block type as everything before the first colon
        if ":" in header:
            first_colon = header.find(":")
            block_type = header[:first_colon].strip()
            remaining = header[first_colon + 1 :].strip() if first_colon + 1 < len(header) else ""

            return {"type": block_type, "remaining_header": remaining}

        # No colon - check for parameters in parentheses
        param_match = re.match(r"([^(]+)\(([^)]*)\)", header)
        if param_match:
            block_type, params_str = param_match.groups()
            return {"type": block_type.strip(), "remaining_header": header}

        # Default: the entire header is the block type
        return {"type": header.strip(), "remaining_header": ""}

    def process_remaining_lines(self) -> list[ExtractedBlock]:
        """Process any remaining lines in the buffer."""
        extracted_blocks = []

        # Process any remaining content in the line buffer
        if self.state.line_buffer:
            lines = self.state.line_buffer.split("\n")

            for line in lines:
                if line.strip():  # Process non-empty lines
                    block = self.process_line(line)
                    if block:
                        self.state.extracted_blocks.append(block)
                        extracted_blocks.append(block)

            # Clear the buffer
            self.state.line_buffer = ""

        return extracted_blocks


def create_block_extraction_processor(block_registry: BlockRegistry, debug: bool = False) -> Callable[[Any, int, float], BlockExtractionMetadata]:
    """
    Create a metadata extractor that processes streaming text for block extraction.

    Args:
        block_registry: Registry of block types and their parsers
        debug: Enable debug output

    Returns:
        A metadata extractor function for use with process_stream
    """
    extractor = BlockExtractor(block_registry, debug)

    def extract_metadata(event: Any, event_number: int, timestamp: float) -> BlockExtractionMetadata:
        """Extract metadata and process blocks from stream events."""

        # Determine the original event type
        original_event_type = "unknown"
        if hasattr(event, "type"):
            original_event_type = str(event.type)
        elif hasattr(event, "__class__"):
            original_event_type = event.__class__.__name__

        # Extract text content from the event
        chunk_data = None

        # Try various common patterns for extracting text
        if hasattr(event, "text"):
            chunk_data = event.text
        elif hasattr(event, "content"):
            chunk_data = event.content
        elif hasattr(event, "chunk"):
            chunk_data = event.chunk
        elif hasattr(event, "delta") and hasattr(event.delta, "content"):
            chunk_data = event.delta.content
        elif isinstance(event, dict):
            chunk_data = event.get("chunk") or event.get("text") or event.get("content")

        # If no text content, return basic metadata
        if not chunk_data:
            return BlockExtractionMetadata(
                timestamp=timestamp,
                event_number=event_number,
                event_type=original_event_type,
                extraction_event_type="non_text_event",
                line_buffer_size=len(extractor.state.line_buffer),
                current_state=extractor.state.current_state_description,
                processed_lines=extractor.state.processed_lines,
                discarded_lines=extractor.state.discarded_lines,
                total_blocks_extracted=len(extractor.state.extracted_blocks),
            )

        # Add chunk to line buffer
        extractor.state.line_buffer += chunk_data

        # Process complete lines
        extracted_block = None
        while "\n" in extractor.state.line_buffer:
            line_end = extractor.state.line_buffer.find("\n")
            line = extractor.state.line_buffer[:line_end]
            extractor.state.line_buffer = extractor.state.line_buffer[line_end + 1 :]

            block = extractor.process_line(line)
            if block:
                extractor.state.extracted_blocks.append(block)
                extracted_block = block
                break  # Return immediately when block is extracted

        # Determine extraction event type
        extraction_event_type = "block_extracted" if extracted_block else "chunk_processed"

        # Log extraction event
        if extracted_block:
            logger.info("Block extracted", **extracted_block.log_context())

        return BlockExtractionMetadata(
            timestamp=timestamp,
            event_number=event_number,
            event_type=original_event_type,
            extraction_event_type=extraction_event_type,
            chunk_data=chunk_data,
            line_buffer_size=len(extractor.state.line_buffer),
            current_state=extractor.state.current_state_description,
            processed_lines=extractor.state.processed_lines,
            discarded_lines=extractor.state.discarded_lines,
            total_blocks_extracted=len(extractor.state.extracted_blocks),
            extracted_block=extracted_block,
        )

    # Store extractor for access to remaining lines processing
    extract_metadata._extractor = extractor

    return extract_metadata


async def process_stream_with_blocks(
    stream: AsyncGenerator[Any, None], block_registry: BlockRegistry | None = None, cancellable: Cancellable | None = None, debug: bool = False
) -> AsyncGenerator[ProcessedEvent[Any, BlockExtractionMetadata], None]:
    """
    Process a stream and extract blocks according to the registry.

    Args:
        stream: The input stream
        block_registry: Registry of block types (uses default if None)
        cancellable: Optional cancellation support
        debug: Enable debug output

    Yields:
        ProcessedEvent instances with BlockExtractionMetadata
    """
    # Use default registry if none provided
    if block_registry is None:
        block_registry = BlockRegistry.create_default()

    # Create the extraction processor
    processor = create_block_extraction_processor(block_registry, debug)

    # Process the stream
    async for event in process_stream(stream, extract_metadata=processor, cancellable=cancellable, metadata_class=BlockExtractionMetadata):
        yield event

        # Check if this was a block extraction
        metadata: BlockExtractionMetadata = event.metadata
        if metadata.extraction_event_type == "block_extracted" and metadata.extracted_block:
            # Report to cancellable if available
            if cancellable:
                await cancellable.report_progress(
                    f"Extracted block: {metadata.extracted_block.block_type}",
                    {"block_hash": metadata.extracted_block.hash_id, "block_type": metadata.extracted_block.block_type, "total_blocks": metadata.total_blocks_extracted},
                )

    # Handle any remaining content
    if hasattr(processor, "_extractor"):
        extractor = processor._extractor

        # Process any remaining lines in the buffer
        remaining_blocks = extractor.process_remaining_lines()

        # Yield each extracted block
        for i, block in enumerate(remaining_blocks):
            final_metadata = BlockExtractionMetadata(
                timestamp=time.time(),
                event_number=extractor.state.processed_lines + i + 1,
                event_type="stream_end",
                extraction_event_type="block_extracted",
                line_buffer_size=0,
                current_state="complete",
                processed_lines=extractor.state.processed_lines,
                discarded_lines=extractor.state.discarded_lines,
                total_blocks_extracted=len(extractor.state.extracted_blocks),
                extracted_block=block,
                remaining_content=None,
            )

            yield ProcessedEvent(original_event=None, metadata=final_metadata)

            # Report the final block
            if cancellable:
                await cancellable.report_progress(
                    f"Extracted final block: {block.block_type}", {"block_hash": block.hash_id, "block_type": block.block_type, "total_blocks": len(extractor.state.extracted_blocks)}
                )

        # Check for any truly incomplete content (blocks without end tags)
        if extractor.state.current_block_hash:
            remaining_lines = [f"!!{extractor.state.current_block_hash}:{extractor.state.current_block_header}"]
            remaining_lines.extend(extractor.state.current_block_lines)
            remaining_content = "\n".join(remaining_lines)

            final_metadata = BlockExtractionMetadata(
                timestamp=time.time(),
                event_number=extractor.state.processed_lines + len(remaining_blocks) + 1,
                event_type="stream_end",
                extraction_event_type="incomplete_content",
                line_buffer_size=0,
                current_state="complete",
                processed_lines=extractor.state.processed_lines,
                discarded_lines=extractor.state.discarded_lines,
                total_blocks_extracted=len(extractor.state.extracted_blocks),
                extracted_block=None,
                remaining_content=remaining_content,
            )

            yield ProcessedEvent(original_event=None, metadata=final_metadata)
