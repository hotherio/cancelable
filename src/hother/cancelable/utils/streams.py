"""
Stream utilities for async cancelation.
"""

from collections.abc import AsyncIterator, Callable
from datetime import timedelta
from typing import TYPE_CHECKING, Any, Optional, TypeVar

import anyio

from hother.cancelable.core.cancelable import Cancelable
from hother.cancelable.utils.logging import get_logger

if TYPE_CHECKING:
    from ..core.token import CancelationToken

logger = get_logger(__name__)

T = TypeVar("T")


async def cancelable_stream(
    stream: AsyncIterator[T],
    timeout: float | timedelta | None = None,
    token: Optional["CancelationToken"] = None,
    report_interval: int | None = None,
    on_progress: Callable[[int, T], Any] | None = None,
    buffer_partial: bool = False,
    operation_id: str | None = None,
    name: str | None = None,
) -> AsyncIterator[T]:
    """
    Make any async iterator cancelable with various options.

    Args:
        stream: Async iterator to wrap
        timeout: Optional timeout for the entire stream
        token: Optional cancelation token
        report_interval: Report progress every N items
        on_progress: Optional progress callback (item_count, latest_item)
        buffer_partial: Whether to buffer items for partial results
        operation_id: Optional operation ID
        name: Optional operation name

    Yields:
        Items from the wrapped stream

    Example:
        async for item in cancelable_stream(
            fetch_items(),
            timeout=30.0,
            report_interval=100,
            on_progress=lambda n, item: print(f"Processed {n} items")
        ):
            process(item)
    """
    # Create appropriate cancelable
    if timeout and token:
        cancelable = Cancelable.with_timeout(timeout, operation_id=operation_id, name=name).combine(
            Cancelable.with_token(token)
        )
    elif timeout:
        cancelable = Cancelable.with_timeout(
            timeout,
            operation_id=operation_id,
            name=name or "stream_timeout",
        )
    elif token:
        cancelable = Cancelable.with_token(
            token,
            operation_id=operation_id,
            name=name or "stream_token",
        )
    else:
        cancelable = Cancelable(
            operation_id=operation_id,
            name=name or "stream",
        )

    # Add progress callback if provided
    if on_progress:

        async def report_wrapper(op_id: str, msg: Any, meta: dict[str, Any] | None):
            if meta and "count" in meta and "latest_item" in meta:
                result = on_progress(meta["count"], meta["latest_item"])
                if hasattr(result, "__await__"):
                    await result

        cancelable.on_progress(report_wrapper)

    # Process stream
    async with cancelable:
        async for item in cancelable.stream(
            stream,
            report_interval=report_interval,
            buffer_partial=buffer_partial,
        ):
            yield item


class CancelableAsyncIterator(AsyncIterator[T]):
    """
    Wrapper class that makes any async iterator cancelable.

    This provides a class-based alternative to the cancelable_stream function.
    """

    def __init__(
        self,
        iterator: AsyncIterator[T],
        cancelable: Cancelable,
        report_interval: int | None = None,
        buffer_partial: bool = False,
    ):
        """
        Initialize cancelable iterator.

        Args:
            iterator: Async iterator to wrap
            cancelable: Cancelable instance to use
            report_interval: Report progress every N items
            buffer_partial: Whether to buffer items
        """
        self._iterator: AsyncIterator[T] = iterator
        self._cancellable: Cancelable = cancelable
        self._report_interval = report_interval
        self._buffer_partial = buffer_partial
        self._count = 0
        self._buffer: list[T] | None = [] if buffer_partial else None
        self._stream_iter = None
        self._completed = False

    def __aiter__(self) -> "CancelableAsyncIterator[T]":
        """Return self as async iterator."""
        return self

    async def __anext__(self) -> T:
        """Get next item with cancelation checking."""
        # Check cancelation
        await self._cancellable.token.check_async()

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
                await self._cancellable.report_progress(
                    f"Processed {self._count} items", {"count": self._count, "latest_item": item}
                )

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

        except Exception:  # Intentionally broad to save partial results on any error
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


async def chunked_cancelable_stream(
    stream: AsyncIterator[T],
    chunk_size: int,
    cancelable: Cancelable,
) -> AsyncIterator[list[T]]:
    """
    Process stream in chunks with cancelation support.

    Args:
        stream: Source async iterator
        chunk_size: Size of chunks to yield
        cancelable: Cancelable instance

    Yields:
        Lists of items (chunks)

    Example:
        async for chunk in chunked_cancelable_stream(items, 100, cancel):
            await process_batch(chunk)
    """
    chunk: list[T] = []

    async for item in cancelable.stream(stream):
        chunk.append(item)

        if len(chunk) >= chunk_size:
            yield chunk
            chunk = []

            # Report progress
            await cancelable.report_progress(f"Processed chunk of {chunk_size} items")

    # Yield remaining items
    if chunk:
        yield chunk
        await cancelable.report_progress(f"Processed final chunk of {len(chunk)} items")
