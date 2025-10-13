"""Core stream simulation functionality."""

import random
import time
from collections.abc import AsyncGenerator

import anyio

from hother.cancelable import Cancellable
from hother.cancelable.utils.logging import configure_logging, get_logger

from .config import StreamConfig
from .utils import get_random_chunk_size

# Configure logging
configure_logging(log_level="INFO")
logger = get_logger(__name__)


async def simulate_stream(text: str, config: StreamConfig | None = None, cancellable: Cancellable | None = None) -> AsyncGenerator[dict, None]:
    """Simulate a more realistic network stream with bursts, stalls, and metadata."""
    if config is None:
        config = StreamConfig()

    start_time = time.time()
    chunk_count = 0

    i = 0
    while i < len(text):
        # Check for cancellation
        if cancellable:
            await cancellable._token.check_async()

        if random.random() < config.stall_probability:
            await anyio.sleep(config.stall_duration)

            if cancellable:
                await cancellable.report_progress(f"Network stall: {config.stall_duration:.3f}s", {"type": "stall", "duration": config.stall_duration})

            yield {"type": "stall", "duration": config.stall_duration, "timestamp": time.time() - start_time}

        if random.random() < config.burst_probability:
            for burst_idx in range(config.burst_size):
                if i >= len(text):
                    break

                # Check for cancellation in burst
                if cancellable:
                    await cancellable._token.check_async()

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
            if cancellable and chunk_count % 10 == 0:
                progress = (i / len(text)) * 100
                await cancellable.report_progress(f"Stream progress: {progress:.1f}%", {"chunks_sent": chunk_count, "bytes_sent": i, "total_bytes": len(text), "progress_percent": progress})

    yield {"type": "complete", "timestamp": time.time() - start_time, "total_chunks": chunk_count}
