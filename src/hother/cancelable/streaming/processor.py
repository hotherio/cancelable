"""Generic stream processing utilities."""

import time
from collections.abc import AsyncGenerator, Callable
from typing import Any, Generic, TypeVar

import anyio
from pydantic import BaseModel, ConfigDict, Field

from hother.cancelable import Cancellable

# Generic type for stream events
T = TypeVar("T")
M = TypeVar("M", bound=BaseModel)


class DefaultMetadata(BaseModel):
    """Default metadata for processed events."""

    timestamp: float = Field(description="Time since stream start")
    event_number: int = Field(description="Sequential event number")
    event_type: str | None = Field(default=None, description="Type of the original event if available")
    extracted_text: str | None = Field(default=None, description="Text extracted from the event")
    content_length: int = Field(default=0, description="Length of extracted content")
    total_content_length: int = Field(default=0, description="Total content length so far")


class ProcessedEvent(BaseModel, Generic[T, M]):
    """Wrapper for processed stream events that preserves the original event."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    original_event: T | None = Field(default=None, description="The original stream event")
    metadata: M | dict[str, Any] = Field(description="Processing metadata")

    def __getattr__(self, name: str) -> Any:
        """Forward attribute access to the original event for compatibility."""
        if name in ["model_config", "model_fields", "model_fields_set", "model_computed_fields"]:
            return super().__getattribute__(name)
        if self.original_event is not None and hasattr(self.original_event, name):
            return getattr(self.original_event, name)
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")


async def process_stream(
    stream: AsyncGenerator[T, None],
    extract_metadata: Callable[[T, int, float], BaseModel | dict[str, Any]] | None = None,
    extract_text: Callable[[T], str] | None = None,
    cancellable: Cancellable | None = None,
    metadata_class: type[BaseModel] | None = None,
) -> AsyncGenerator[ProcessedEvent[T, Any], None]:
    """
    Process any async stream generically, extracting metadata from events.

    Args:
        stream: The original async generator/stream
        extract_metadata: Optional function to extract custom metadata from events
        extract_text: Optional function to extract text content from events
        cancellable: Optional cancellation support
        metadata_class: Optional metadata class to use (defaults to DefaultMetadata)

    Yields:
        ProcessedEvent instances containing both original event and metadata
    """
    start_time = time.time()
    event_number = 0
    total_content_length = 0

    # Use provided metadata class or default
    if metadata_class is None and extract_metadata is None:
        metadata_class = DefaultMetadata

    async for event in stream:
        # Check for cancellation
        if cancellable:
            await cancellable._token.check_async()

        event_number += 1
        current_time = time.time() - start_time

        # Extract metadata using custom function if provided
        if extract_metadata:
            metadata = extract_metadata(event, event_number, current_time)
        else:
            # Build default metadata
            extracted_text = None
            content_length = 0

            if extract_text:
                try:
                    extracted_text = extract_text(event)
                    if extracted_text:
                        content_length = len(extracted_text)
                        total_content_length += content_length
                except (ValueError, TypeError, AttributeError, anyio.get_cancelled_exc_class()):
                    pass  # Ignore extraction errors

            # Determine event type
            event_type = None
            if hasattr(event, "type"):
                event_type = str(event.type)
            elif hasattr(event, "__class__"):
                event_type = event.__class__.__name__

            # Create metadata instance
            if metadata_class:
                metadata = metadata_class(
                    timestamp=current_time, event_number=event_number, event_type=event_type, extracted_text=extracted_text, content_length=content_length, total_content_length=total_content_length
                )
            else:
                metadata = {
                    "timestamp": current_time,
                    "event_number": event_number,
                    "event_type": event_type,
                    "extracted_text": extracted_text,
                    "content_length": content_length,
                    "total_content_length": total_content_length,
                }

        # Yield the processed event
        yield ProcessedEvent(original_event=event, metadata=metadata)

        # Report progress periodically
        if cancellable and event_number % 10 == 0:
            await cancellable.report_progress(f"Processed {event_number} events", {"events_processed": event_number, "total_content_length": total_content_length, "elapsed_time": current_time})


# Specialized metadata classes for common use cases
class StreamMetadata(BaseModel):
    """Metadata for streaming responses (e.g., LLM streams)."""

    timestamp: float
    event_number: int
    event_type: str | None = None
    content: str | None = None
    content_length: int = 0
    total_content: str = ""
    is_final: bool = False
    chunk_id: str | None = None
    model: str | None = None


class BlockMetadata(BaseModel):
    """Metadata for block-based processing."""

    timestamp: float
    event_number: int
    block_type: str | None = None
    block_id: str | None = None
    block_index: int | None = None
    content: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    is_complete: bool = False


# Helper functions for common extraction patterns
def create_llm_metadata_extractor(accumulate_content: bool = True) -> Callable[[Any, int, float], StreamMetadata]:
    """Create metadata extractor for LLM streams."""
    accumulated_content = ""

    def extract(event: Any, event_number: int, timestamp: float) -> StreamMetadata:
        nonlocal accumulated_content

        content = None
        is_final = False
        event_type = None

        # Extract event type
        if hasattr(event, "type"):
            event_type = str(event.type)

        # Extract content based on common patterns
        if hasattr(event, "text"):
            content = event.text
        elif hasattr(event, "content"):
            content = event.content
        elif hasattr(event, "delta") and hasattr(event.delta, "content"):
            content = event.delta.content
        elif hasattr(event, "choices") and event.choices:
            choice = event.choices[0]
            if hasattr(choice, "delta") and hasattr(choice.delta, "content"):
                content = choice.delta.content

        # Check if this is a final event
        if event_type in ["content_block_stop", "message_stop", "stop", "done"]:
            is_final = True

        # Accumulate content if requested
        if accumulate_content and content:
            accumulated_content += content

        return StreamMetadata(
            timestamp=timestamp,
            event_number=event_number,
            event_type=event_type,
            content=content,
            content_length=len(content) if content else 0,
            total_content=accumulated_content if accumulate_content else "",
            is_final=is_final,
            model=getattr(event, "model", None),
        )

    return extract
