"""Integration tests for block extraction system."""

import asyncio
from typing import AsyncGenerator

# Use pytest.mark.anyio if using anyio, or keep pytest.mark.asyncio if using pytest-asyncio
import anyio
import pytest

from hother.cancelable.streaming.blocks import BlockRegistry, process_stream_with_blocks


async def create_test_stream(content: str) -> AsyncGenerator[dict, None]:
    """Create a test stream from content."""
    # Yield content in chunks
    chunk_size = 20
    for i in range(0, len(content), chunk_size):
        chunk = content[i : i + chunk_size]
        yield {"type": "text", "content": chunk}
        await anyio.sleep(0.01)


@pytest.mark.anyio  # Changed from pytest.mark.asyncio
async def test_extract_single_block():
    """Test extracting a single block."""
    content = """Some text before
!!test01:simple
This is simple content
!!test01:end
Some text after"""

    registry = BlockRegistry.create_default()
    blocks = []

    async for event in process_stream_with_blocks(create_test_stream(content), block_registry=registry):
        if event.metadata.extraction_event_type == "block_extracted":
            blocks.append(event.metadata.extracted_block)

    assert len(blocks) == 1
    assert blocks[0].hash_id == "test01"
    assert blocks[0].block_type == "simple"
    assert blocks[0].content == "This is simple content"


@pytest.mark.anyio  # Changed from pytest.mark.asyncio
async def test_extract_multiple_blocks():
    """Test extracting multiple blocks of different types."""
    content = """
!!hier01:hierarchy
src/
├── main.py
└── utils.py
!!hier01:end

!!file01:files_operations
src/main.py:C
src/utils.py:C
!!file01:end

!!actn01:a:process:after()
<input>data.csv</input>
!!actn01:end
"""

    registry = BlockRegistry.create_default()
    blocks = []

    async for event in process_stream_with_blocks(create_test_stream(content), block_registry=registry):
        if event.metadata.extraction_event_type == "block_extracted":
            blocks.append(event.metadata.extracted_block)

    assert len(blocks) == 3

    # Check hierarchy block
    hier_block = next(b for b in blocks if b.block_type == "hierarchy")
    assert hier_block.content.file_count == 2
    assert hier_block.content.folder_count == 0

    # Check files block
    files_block = next(b for b in blocks if b.block_type == "files_operations")
    assert len(files_block.content.operations["create"]) == 2

    # Check action block
    action_block = next(b for b in blocks if b.block_type == "a")
    assert action_block.content.parameters["input"] == "data.csv"


@pytest.mark.anyio  # Changed from pytest.mark.asyncio
async def test_incomplete_block_handling():
    """Test handling of incomplete blocks."""
    content = """
!!test01:simple
This block has no end tag
"""

    registry = BlockRegistry.create_default()
    blocks = []
    incomplete_content = None

    async for event in process_stream_with_blocks(create_test_stream(content), block_registry=registry):
        if event.metadata.extraction_event_type == "block_extracted":
            blocks.append(event.metadata.extracted_block)
        elif event.metadata.extraction_event_type == "incomplete_content":
            incomplete_content = event.metadata.remaining_content

    assert len(blocks) == 0
    assert incomplete_content is not None
    assert "!!test01:simple" in incomplete_content


@pytest.mark.anyio  # Changed from pytest.mark.asyncio
async def test_nested_content():
    """Test blocks containing block-like syntax in content."""
    content = """
!!test01:simple
This content has !!fake01:block syntax
But it's just content, not a real block
!!test01:end
"""

    registry = BlockRegistry.create_default()
    blocks = []

    async for event in process_stream_with_blocks(create_test_stream(content), block_registry=registry):
        if event.metadata.extraction_event_type == "block_extracted":
            blocks.append(event.metadata.extracted_block)

    assert len(blocks) == 1
    assert "!!fake01:block" in blocks[0].content


@pytest.mark.anyio  # Changed from pytest.mark.asyncio
async def test_cancellation():
    """Test cancellation support."""
    from hother.cancelable import Cancellable, CancellationToken

    content = """
!!test01:simple
First block
!!test01:end

!!test02:simple
Second block
!!test02:end

!!test03:simple
Third block
!!test03:end
"""

    token = CancellationToken()
    operation = Cancellable.with_token(token, name="test_cancellation")

    registry = BlockRegistry.create_default()
    blocks = []

    async def cancel_after_first_block():
        """Cancel after first block is extracted."""
        while len(blocks) < 1:
            await anyio.sleep(0.01)
        await token.cancel()

    try:
        async with anyio.create_task_group() as tg:
            tg.start_soon(cancel_after_first_block)

            async with operation:
                async for event in process_stream_with_blocks(create_test_stream(content), block_registry=registry, cancellable=operation):
                    if event.metadata.extraction_event_type == "block_extracted":
                        blocks.append(event.metadata.extracted_block)
    except asyncio.CancelledError:
        pass

    # Should only have extracted one block before cancellation
    assert len(blocks) == 1
    assert blocks[0].hash_id == "test01"
