"""Core stream simulation functionality."""

import logging
import random
import time
from collections.abc import AsyncGenerator
from typing import Any

import anyio

from hother.cancelable import Cancelable

from .config import StreamConfig
from .utils import get_random_chunk_size

logger = logging.getLogger(__name__)


async def simulate_stream(
    text: str, config: StreamConfig | None = None, cancelable: Cancelable | None = None
) -> AsyncGenerator[dict[str, Any], None]:
    """
    Simulate a realistic network stream with variable timing and cancellation support.

    This function simulates network streaming behavior including bursts, stalls,
    jitter, and variable chunk sizes. It's useful for testing cancellable stream
    processing and demonstrating async cancellation patterns.

    Args:
        text: The text content to stream
        config: Optional StreamConfig to control simulation behavior.
            If None, uses default configuration.
        cancelable: Optional Cancelable instance for cancellation support.
            If provided, the stream will check for cancellation and report progress.

    Yields:
        Dictionary chunks with the following types:
        - {"type": "data", "chunk": str, "chunk_size": int, ...} - Data chunks
        - {"type": "stall", "duration": float, ...} - Network stalls
        - {"type": "complete", "total_chunks": int, ...} - Stream completion

    Raises:
        CancelledError: If the associated Cancelable is cancelled during streaming

    Example:
        ```python
        async with Cancelable.with_timeout(5.0) as cancel:
            config = StreamConfig(base_delay=0.1, stall_probability=0.1)

            async for event in simulate_stream("Hello world", config, cancel):
                if event["type"] == "data":
                    print(event["chunk"], end="", flush=True)
        ```
    """
    if config is None:
        config = StreamConfig()

    start_time = time.time()
    chunk_count = 0

    i = 0
    while i < len(text):
        # Check for cancelation
        if cancelable:
            await cancelable.token.check_async()

        if random.random() < config.stall_probability:
            await anyio.sleep(config.stall_duration)

            if cancelable:
                await cancelable.report_progress(
                    f"Network stall: {config.stall_duration:.3f}s", {"type": "stall", "duration": config.stall_duration}
                )

            yield {"type": "stall", "duration": config.stall_duration, "timestamp": time.time() - start_time}

        if random.random() < config.burst_probability:
            for _ in range(config.burst_size):
                if i >= len(text):
                    break

                # Check for cancelation in burst
                if cancelable:
                    await cancelable.token.check_async()

                chunk_size = get_random_chunk_size(config)
                chunk = text[i : i + chunk_size]
                i += len(chunk)
                chunk_count += 1

                yield {
                    "type": "data",
                    "chunk": chunk,
                    "chunk_size": len(chunk),
                    "requested_chunk_size": chunk_size,
                    "position": i,
                    "total_length": len(text),
                    "timestamp": time.time() - start_time,
                    "burst": True,
                    "chunk_number": chunk_count,
                }

                await anyio.sleep(0.001)
        else:
            chunk_size = get_random_chunk_size(config)
            chunk = text[i : i + chunk_size]
            i += len(chunk)
            chunk_count += 1

            delay = config.base_delay
            if random.random() < config.jitter_probability:
                delay += random.uniform(-config.jitter, config.jitter)
            delay = max(0, delay)

            await anyio.sleep(delay)

            yield {
                "type": "data",
                "chunk": chunk,
                "chunk_size": len(chunk),
                "requested_chunk_size": chunk_size,
                "position": i,
                "total_length": len(text),
                "timestamp": time.time() - start_time,
                "burst": False,
                "chunk_number": chunk_count,
            }

            # Report progress periodically
            if cancelable and chunk_count % 10 == 0:
                progress = (i / len(text)) * 100
                await cancelable.report_progress(
                    f"Stream progress: {progress:.1f}%",
                    {
                        "chunks_sent": chunk_count,
                        "bytes_sent": i,
                        "total_bytes": len(text),
                        "progress_percent": progress,
                    },
                )

    yield {"type": "complete", "timestamp": time.time() - start_time, "total_chunks": chunk_count}
