"""
Basic usage example for the block extraction system.
"""

from collections.abc import AsyncGenerator

import anyio

from cancelable import Cancellable
from cancelable.streaming.blocks import BlockRegistry, process_stream_with_blocks
from cancelable.utils.logging import configure_logging, get_logger

# Configure logging
configure_logging(log_level="INFO")
logger = get_logger(__name__)


async def example_stream() -> AsyncGenerator[dict, None]:
    """Generate an example stream with various block types."""
    content = """Let's create a project structure:

!!hier01:hierarchy
project/
├── src/
│   ├── main.py
│   └── utils.py
├── tests/
└── README.md
!!hier01:end

Now let's define file operations:

!!file01:files_operations
src/main.py:C
src/utils.py:C
tests/test_main.py:C
README.md:E
!!file01:end

Here are the setup instructions:

!!inst01:instruction(setup, test, deploy)
Setup: Create virtual environment
Test: Run pytest
Deploy: Push to production
!!inst01:end

And an action with dependencies:

!!actn01:a:build:after(file01)
<output_dir>dist/</output_dir>
<config>production.json</config>
!!actn01:end
"""

    # Simulate streaming by yielding chunks
    chunk_size = 50
    for i in range(0, len(content), chunk_size):
        chunk = content[i : i + chunk_size]
        yield {"type": "text", "content": chunk}
        await anyio.sleep(0.1)  # Simulate network delay


async def main():
    """Main example function."""
    logger.info("Starting block extraction example")

    # Create a cancellable operation
    operation = Cancellable(name="example_extraction")

    # Use default block registry
    registry = BlockRegistry.create_default()

    # Track extracted blocks
    extracted_blocks = []

    async with operation:
        async for event in process_stream_with_blocks(example_stream(), block_registry=registry, cancellable=operation, debug=False):
            # Access original event
            if event.original_event and "content" in event.original_event:
                print(event.original_event["content"], end="", flush=True)

            # Check for extracted blocks
            if event.metadata.extraction_event_type == "block_extracted":
                block = event.metadata.extracted_block
                extracted_blocks.append(block)

                # Get the parser to format the block
                parser = registry.get_parser(block.block_type)
                if parser:
                    parser.format_block(block)

                logger.info(f"Extracted {block.block_type} block", **block.log_context())

    # Summary
    print(f"\n\n{'=' * 60}")
    print("Extraction Summary:")
    print(f"  Total blocks: {len(extracted_blocks)}")
    print(f"  Block types: {set(b.block_type for b in extracted_blocks)}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    anyio.run(main)
