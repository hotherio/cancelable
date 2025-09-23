"""
Tests for stream utilities.
"""

import anyio
import pytest

from cancelable import Cancellable, CancellationToken
from cancelable.utils.streams import CancellableAsyncIterator, cancellable_stream, chunked_cancellable_stream


class TestCancellableStream:
    """Test cancellable_stream function."""

    @pytest.mark.anyio
    async def test_basic_stream(self):
        """Test basic stream wrapping."""

        async def number_stream():
            for i in range(5):
                yield i
                await anyio.sleep(0.01)

        items = []
        async for item in cancellable_stream(number_stream()):
            items.append(item)

        assert items == [0, 1, 2, 3, 4]

    @pytest.mark.anyio
    async def test_stream_with_timeout(self):
        """Test stream with timeout."""

        async def slow_stream():
            i = 0
            while True:
                yield i
                i += 1
                await anyio.sleep(0.05)

        items = []
        with pytest.raises(anyio.get_cancelled_exc_class()):
            async for item in cancellable_stream(slow_stream(), timeout=0.15):
                items.append(item)

        # Should get ~3 items before timeout
        assert 2 <= len(items) <= 4

    @pytest.mark.anyio
    async def test_chunked_progress_with_remainder(self):
        """Test chunked stream progress reporting with final partial chunk."""

        async def source():
            for i in range(22):  # 22 items = 4 chunks of 5 + 1 chunk of 2
                yield i

        progress_messages = []

        def capture_progress(op_id, msg, meta):
            if "chunk" in msg:
                progress_messages.append(msg)

        cancellable = Cancellable().on_progress(capture_progress)
        chunks = []

        async with cancellable:
            async for chunk in chunked_cancellable_stream(source(), chunk_size=5, cancellable=cancellable):
                chunks.append(chunk)

        assert len(chunks) == 5
        assert len(progress_messages) == 5
        # First 4 are full chunks
        for i in range(4):
            assert "Processed chunk of 5 items" in progress_messages[i]
        # Last one is partial
        assert "Processed final chunk of 2 items" in progress_messages[-1]

    @pytest.mark.anyio
    async def test_stream_with_token(self):
        """Test stream with cancellation token."""
        token = CancellationToken()

        async def infinite_stream():
            i = 0
            while True:
                yield i
                i += 1
                await anyio.sleep(0.01)

        async def cancel_after_delay():
            await anyio.sleep(0.1)
            await token.cancel()

        items = []

        async with anyio.create_task_group() as tg:
            tg.start_soon(cancel_after_delay)

            with pytest.raises(anyio.get_cancelled_exc_class()):
                async for item in cancellable_stream(infinite_stream(), token=token):
                    items.append(item)

        assert len(items) > 5  # Should process several items

    @pytest.mark.anyio
    async def test_stream_with_progress(self):
        """Test stream with progress reporting."""
        progress_reports = []

        async def number_stream():
            for i in range(25):
                yield i
                await anyio.sleep(0.001)

        def on_progress(count: int, item: int):
            progress_reports.append((count, item))

        items = []
        async for item in cancellable_stream(number_stream(), report_interval=10, on_progress=on_progress):
            items.append(item)

        assert len(items) == 25
        assert len(progress_reports) == 2  # At 10 and 20 items
        assert progress_reports[0] == (10, 9)  # 10th item (0-indexed)
        assert progress_reports[1] == (20, 19)  # 20th item

    @pytest.mark.anyio
    async def test_stream_combined_cancellation(self):
        """Test stream with both timeout and token."""
        token = CancellationToken()

        async def stream():
            for i in range(100):
                yield i
                await anyio.sleep(0.01)

        # Token will cancel before timeout
        async def cancel_soon():
            await anyio.sleep(0.05)
            await token.cancel()

        items = []

        async with anyio.create_task_group() as tg:
            tg.start_soon(cancel_soon)

            with pytest.raises(anyio.get_cancelled_exc_class()):
                async for item in cancellable_stream(
                    stream(),
                    timeout=1.0,  # Long timeout
                    token=token,
                ):
                    items.append(item)

        assert len(items) < 10  # Cancelled early by token


class TestCancellableAsyncIterator:
    """Test CancellableAsyncIterator class."""

    @pytest.mark.anyio
    async def test_iterator_basic(self):
        """Test basic iterator functionality."""

        async def source():
            for i in range(5):
                yield i

        cancellable = Cancellable()
        iterator = CancellableAsyncIterator(source(), cancellable)

        items = []
        async with cancellable:
            async for item in iterator:
                items.append(item)

        assert items == [0, 1, 2, 3, 4]

    @pytest.mark.anyio
    async def test_iterator_cancellation(self):
        """Test iterator cancellation."""

        async def infinite():
            i = 0
            while True:
                yield i
                i += 1
                await anyio.sleep(0.01)

        cancellable = Cancellable.with_timeout(0.1)
        iterator = CancellableAsyncIterator(infinite(), cancellable)

        items = []

        with pytest.raises(anyio.get_cancelled_exc_class()):
            async with cancellable:
                async for item in iterator:
                    items.append(item)

        assert len(items) > 0
        assert iterator._count == len(items)

    @pytest.mark.anyio
    async def test_iterator_progress_reporting(self):
        """Test iterator with progress reporting."""

        async def source():
            for i in range(25):
                yield i
                await anyio.sleep(0.001)

        progress_counts = []

        def capture_progress(op_id, msg, meta):
            if meta and "count" in meta:
                progress_counts.append(meta["count"])

        cancellable = Cancellable().on_progress(capture_progress)
        iterator = CancellableAsyncIterator(source(), cancellable, report_interval=10)

        async with cancellable:
            items = [item async for item in iterator]

        assert len(items) == 25
        assert progress_counts == [10, 20]

    @pytest.mark.anyio
    async def test_iterator_buffering(self):
        """Test iterator with partial result buffering."""

        async def source():
            for i in range(20):
                yield f"item_{i}"
                await anyio.sleep(0.01)

        cancellable = Cancellable.with_timeout(0.15)
        iterator = CancellableAsyncIterator(source(), cancellable, buffer_partial=True)

        try:
            async with cancellable:
                async for _ in iterator:
                    pass
        except anyio.get_cancelled_exc_class():
            pass

        # Check partial results
        partial = cancellable.context.partial_result
        assert partial is not None
        assert "count" in partial
        assert "buffer" in partial
        assert partial["completed"] is False
        assert len(partial["buffer"]) > 0
        assert all(item.startswith("item_") for item in partial["buffer"])

    @pytest.mark.anyio
    async def test_iterator_aclose(self):
        """Test iterator cleanup with aclose."""
        close_called = False

        class CloseableIterator:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise StopAsyncIteration

            async def aclose(self):
                nonlocal close_called
                close_called = True

        cancellable = Cancellable()
        iterator = CancellableAsyncIterator(CloseableIterator(), cancellable)

        async with cancellable:
            async for _ in iterator:
                pass

        await iterator.aclose()
        assert close_called


class TestChunkedCancellableStream:
    """Test chunked_cancellable_stream function."""

    @pytest.mark.anyio
    async def test_chunked_basic(self):
        """Test basic chunked streaming."""

        async def source():
            for i in range(10):
                yield i

        cancellable = Cancellable()
        chunks = []

        async with cancellable:
            async for chunk in chunked_cancellable_stream(source(), chunk_size=3, cancellable=cancellable):
                chunks.append(chunk)

        assert len(chunks) == 4  # 3, 3, 3, 1
        assert chunks[0] == [0, 1, 2]
        assert chunks[1] == [3, 4, 5]
        assert chunks[2] == [6, 7, 8]
        assert chunks[3] == [9]

    @pytest.mark.anyio
    async def test_chunked_exact_size(self):
        """Test chunked stream with exact chunk size."""

        async def source():
            for i in range(9):
                yield i

        cancellable = Cancellable()
        chunks = []

        async with cancellable:
            async for chunk in chunked_cancellable_stream(source(), chunk_size=3, cancellable=cancellable):
                chunks.append(chunk)

        assert len(chunks) == 3
        assert all(len(chunk) == 3 for chunk in chunks)

    @pytest.mark.anyio
    async def test_chunked_cancellation(self):
        """Test chunked stream with cancellation."""

        async def infinite_source():
            i = 0
            while True:
                yield i
                i += 1
                await anyio.sleep(0.01)

        cancellable = Cancellable.with_timeout(0.15)
        chunks = []

        with pytest.raises(anyio.get_cancelled_exc_class()):
            async with cancellable:
                async for chunk in chunked_cancellable_stream(infinite_source(), chunk_size=5, cancellable=cancellable):
                    chunks.append(chunk)

        # Should have processed some chunks
        assert len(chunks) > 0
        assert all(len(chunk) == 5 for chunk in chunks[:-1])

    @pytest.mark.anyio
    async def test_chunked_progress(self):
        """Test chunked stream progress reporting."""

        async def source():
            for i in range(20):
                yield i

        progress_messages = []

        def capture_progress(op_id, msg, meta):
            if "chunk" in msg:
                progress_messages.append(msg)

        cancellable = Cancellable().on_progress(capture_progress)
        chunks = []

        async with cancellable:
            async for chunk in chunked_cancellable_stream(source(), chunk_size=5, cancellable=cancellable):
                chunks.append(chunk)

        assert len(chunks) == 4
        assert len(progress_messages) == 4
        # All chunks are exactly 5 items, so no "final" chunk
        assert all("Processed chunk of 5 items" in msg for msg in progress_messages)

    @pytest.mark.anyio
    async def test_chunked_empty_stream(self):
        """Test chunked stream with empty source."""

        async def empty_source():
            return
            yield  # Make it a generator

        cancellable = Cancellable()
        chunks = []

        async with cancellable:
            async for chunk in chunked_cancellable_stream(empty_source(), chunk_size=5, cancellable=cancellable):
                chunks.append(chunk)

        assert chunks == []
