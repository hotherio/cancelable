# Streaming Cancelation

The primary reason why Cancelable was developed is to managed properly stream cancelable, and in particular in the context of canceling async streams from another thread or processe.

## Overview

**Streaming cancelation** is a core feature of Cancelable that allows you to safely cancel async stream processing operations. 

## Basic Stream Cancelation

### Simple Stream with Timeout

```python
from hother.cancelable import Cancelable, cancelable_stream
import anyio

async def process_stream():
    async with Cancelable.with_timeout(60.0, name="stream_processor") as cancel:
        async for item in cancelable_stream(data_source(), cancel): # (1)!
            await process_item(item)
            # Stream automatically stops on timeout

anyio.run(process_stream)
```

1. `cancelable_stream()` wraps any async iterator to make it cancelation-aware

### Manual Stream Cancelation

```python
from hother.cancelable import CancelationToken

token = CancelationToken()

async def stream_worker():
    async with Cancelable.with_token(token) as cancel:
        async for item in cancelable_stream(data(), cancel):
            await process(item)

async def stream_controller():
    await anyio.sleep(10)
    await token.cancel("User stopped stream")

# Run both
async with anyio.create_task_group() as tg:
    tg.start_soon(stream_worker)
    tg.start_soon(stream_controller)
```

## The cancelable_stream Utility

The `cancelable_stream()` function wraps any async iterator to make it respect cancelation:

```python
from hother.cancelable.utils.streams import cancelable_stream

async with Cancelable.with_timeout(30.0) as cancel:
    # Wrap any async iterator
    wrapped = cancelable_stream(
        async_iterator=my_stream(),  # Any async generator
        cancelable=cancel,           # Cancelable context
        buffer_size=100               # Optional buffering
    )

    async for item in wrapped:
        await process(item)
```

### How It Works

`cancelable_stream()` monitors the cancelable context and:

1. **Yields items** from the source stream normally
2. **Checks cancelation** before each yield
3. **Stops iteration** cleanly if cancelled
4. **Handles buffering** to prevent backpressure

## Class-Based Iterator

### CancelableAsyncIterator

Class-based alternative to `cancelable_stream()`:

```python
from hother.cancelable.utils.streams import CancelableAsyncIterator

async with Cancelable.with_timeout(60.0) as cancel:
    # Wrap any async iterator
    stream = CancelableAsyncIterator(data_source(), cancel)

    async for item in stream:
        await process(item)
        # Stream automatically stops on cancelation
```

**Features**:
- Implements `__aiter__` and `__anext__`
- Checks cancelation before each item
- Graceful termination

**Use case**: When you need more control over stream iteration or prefer class-based APIs.

## Chunked Processing

### chunked_cancellable_stream()

Process streams in chunks with cancelation support:

```python
from hother.cancelable.utils.streams import chunked_cancellable_stream

async with Cancelable.with_timeout(300.0) as cancel:
    # Process in chunks of 100 items
    async for chunk in chunked_cancellable_stream(
        data_stream(),
        cancel,
        chunk_size=100
    ):
        # chunk is a list of up to 100 items
        await batch_process(chunk)
        # Cancelation checked between chunks
```

**Parameters**:
- `stream` - Source async iterator
- `cancelable` - Cancelable context
- `chunk_size` - Items per chunk

**Use cases**:
- Batch database inserts
- Bulk API calls
- Memory-efficient processing
