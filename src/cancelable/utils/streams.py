"""
Stream utilities for async cancellation.
"""

from collections.abc import AsyncIterator, Callable
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Optional, TypeVar

import anyio

from cancelable.core.cancellable import Cancellable
from cancelable.utils.logging import get_logger

if TYPE_CHECKING:
    from ..core.token import CancellationToken

logger = get_logger(__name__)

T = TypeVar("T")


async def cancellable_stream(
    stream: AsyncIterator[T],
    timeout: float | timedelta | None = None,
    token: Optional["CancellationToken"] = None,
    report_interval: int | None = None,
    on_progress: Callable[[int, T], Any] | None = None,
    buffer_partial: bool = False,
    operation_id: str | None = None,
    name: str | None = None,
) -> AsyncIterator[T]:
    """
    Make any async iterator cancellable with various options.

    Args:
        stream: Async iterator to wrap
        timeout: Optional timeout for the entire stream
        token: Optional cancellation token
        report_interval: Report progress every N items
        on_progress: Optional progress callback (item_count, latest_item)
        buffer_partial: Whether to buffer items for partial results
        operation_id: Optional operation ID
        name: Optional operation name

    Yields:
        Items from the wrapped stream

    Example:
        async for item in cancellable_stream(
            fetch_items(),
            timeout=30.0,
            report_interval=100,
            on_progress=lambda n, item: print(f"Processed {n} items")
        ):
            process(item)
    """
    # Create appropriate cancellable
    if timeout and token:
        cancellable = Cancellable.with_timeout(timeout, operation_id=operation_id, name=name).combine(Cancellable.with_token(token))
    elif timeout:
        cancellable = Cancellable.with_timeout(
            timeout,
            operation_id=operation_id,
            name=name or "stream_timeout",
        )
    elif token:
        cancellable = Cancellable.with_token(
            token,
            operation_id=operation_id,
            name=name or "stream_token",
        )
    else:
        cancellable = Cancellable(
            operation_id=operation_id,
            name=name or "stream",
        )

    # Add progress callback if provided
    if on_progress:

        async def report_wrapper(op_id: str, msg: str, meta: dict[str, Any]):
            if meta and "count" in meta and "latest_item" in meta:
                result = on_progress(meta["count"], meta["latest_item"])
                if hasattr(result, "__await__"):
                    await result

        cancellable.on_progress(report_wrapper)

    # Process stream
    async with cancellable:
        async for item in cancellable.stream(
            stream,
            report_interval=report_interval,
            buffer_partial=buffer_partial,
        ):
            yield item


class CancellableAsyncIterator(AsyncIterator[T]):
    """
    Wrapper class that makes any async iterator cancellable.

    This provides a class-based alternative to the cancellable_stream function.
    """

    def __init__(
        self,
        iterator: AsyncIterator[T],
        cancellable: Cancellable,
        report_interval: int | None = None,
        buffer_partial: bool = False,
    ):
        """
        Initialize cancellable iterator.

        Args:
            iterator: Async iterator to wrap
            cancellable: Cancellable instance to use
            report_interval: Report progress every N items
            buffer_partial: Whether to buffer items
        """
        self._iterator = iterator
        self._cancellable = cancellable
        self._report_interval = report_interval
        self._buffer_partial = buffer_partial
        self._count = 0
        self._buffer = [] if buffer_partial else None
        self._stream_iter = None
        self._completed = False

    def __aiter__(self) -> "CancellableAsyncIterator[T]":
        """Return self as async iterator."""
        return self

    async def __anext__(self) -> T:
        """Get next item with cancellation checking."""
        # Check cancellation
        await self._cancellable._token.check_async()

        try:
            # Get next item
            item = await self._iterator.__anext__()

            # Update count and buffer
            self._count += 1
            if self._buffer is not None:
                self._buffer.append(item)
                if len(self._buffer) > 1000:
                    self._buffer = self._buffer[-1000:]

            # Report progress if needed
            if self._report_interval and self._count % self._report_interval == 0:
                await self._cancellable.report_progress(f"Processed {self._count} items", {"count": self._count, "latest_item": item})

            return item

        except StopAsyncIteration:
            # Stream ended normally
            self._completed = True
            if self._buffer is not None:
                self._cancellable.context.partial_result = {
                    "count": self._count,
                    "buffer": self._buffer,
                    "completed": True,
                }
            raise

        except anyio.get_cancelled_exc_class():
            # Cancelled
            if self._buffer is not None:
                self._cancellable.context.partial_result = {
                    "count": self._count,
                    "buffer": self._buffer,
                    "completed": False,
                }
            raise

        except Exception:
            # Error
            if self._buffer is not None:
                self._cancellable.context.partial_result = {
                    "count": self._count,
                    "buffer": self._buffer,
                    "completed": False,
                }
            raise

    async def aclose(self) -> None:
        """Close the iterator."""
        if hasattr(self._iterator, "aclose"):
            await self._iterator.aclose()


async def chunked_cancellable_stream(
    stream: AsyncIterator[T],
    chunk_size: int,
    cancellable: Cancellable,
) -> AsyncIterator[list[T]]:
    """
    Process stream in chunks with cancellation support.

    Args:
        stream: Source async iterator
        chunk_size: Size of chunks to yield
        cancellable: Cancellable instance

    Yields:
        Lists of items (chunks)

    Example:
        async for chunk in chunked_cancellable_stream(items, 100, cancel):
            await process_batch(chunk)
    """
    chunk = []

    async for item in cancellable.stream(stream):
        chunk.append(item)

        if len(chunk) >= chunk_size:
            yield chunk
            chunk = []

            # Report progress
            await cancellable.report_progress(f"Processed chunk of {chunk_size} items")

    # Yield remaining items
    if chunk:
        yield chunk
        await cancellable.report_progress(f"Processed final chunk of {len(chunk)} items")
