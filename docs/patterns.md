# Common Patterns and Best Practices

## Pattern: Graceful Shutdown

Handle application shutdown gracefully:

```python
import signal
from hother.cancelable import Cancellable

async def main():
    # Handle SIGINT and SIGTERM
    async with Cancellable.with_signal(signal.SIGINT, signal.SIGTERM) as cancel:
        cancel.on_cancel(lambda ctx: print("Shutting down gracefully..."))

        # Your application logic
        await run_application()
```

## Pattern: Resource Cleanup

Ensure resources are cleaned up even on cancellation:

```python
async def process_with_cleanup():
    resource = None

    async with Cancellable.with_timeout(30) as cancel:
        try:
            # Acquire resource
            resource = await acquire_resource()

            # Process
            result = await process(resource)

            return result

        finally:
            # Shield cleanup from cancellation
            if resource:
                async with cancel.shield():
                    await resource.cleanup()
```

## Pattern: Batch Processing with Progress

Process data in batches with progress reporting:

```python
async def process_large_dataset(data: List[Any], batch_size: int = 100):
    async with Cancellable(name="batch_processing") as cancel:
        cancel.on_progress(lambda op_id, msg, meta: logger.info(msg, **meta))

        total = len(data)
        processed = 0

        for i in range(0, total, batch_size):
            batch = data[i:i + batch_size]

            # Process batch
            await process_batch(batch)
            processed += len(batch)

            # Report progress
            progress = (processed / total) * 100
            await cancel.report_progress(
                f"Processed {processed}/{total} items",
                {"progress_percent": progress, "batch_number": i // batch_size + 1}
            )
```

## Pattern: Retry with Cancellation

Implement retry logic with cancellation support:

```python
async def retry_with_cancellation(
    operation: Callable,
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
):
    async with Cancellable(name="retry_operation") as cancel:
        last_error = None

        for attempt in range(max_retries):
            try:
                # Check cancellation before retry
                await cancel._token.check_async()

                # Attempt operation
                result = await operation()
                return result

            except Exception as e:
                last_error = e

                if attempt < max_retries - 1:
                    await cancel.report_progress(
                        f"Attempt {attempt + 1} failed, retrying...",
                        {"error": str(e)}
                    )

                    # Wait with exponential backoff
                    await anyio.sleep(delay)
                    delay *= backoff

        raise last_error
```

## Pattern: Concurrent Operations with Shared Cancellation

Run multiple operations with shared cancellation:

```python
async def parallel_operations():
    async with Cancellable(name="parallel_work") as cancel:
        async def worker(worker_id: int, items: List[Any]):
            for item in items:
                # Check cancellation
                await cancel._token.check_async()

                # Process item
                await process_item(item)

                # Report progress
                await cancel.report_progress(
                    f"Worker {worker_id} processed item",
                    {"worker_id": worker_id, "item": item}
                )

        # Split work among workers
        work_items = split_into_chunks(all_items, worker_count=4)

        # Run workers concurrently
        async with anyio.create_task_group() as tg:
            for i, items in enumerate(work_items):
                tg.start_soon(worker, i, items)
```

## Pattern: Hierarchical Cancellation

Create operation hierarchies with parent-child relationships:

```python
async def hierarchical_operations():
    async with Cancellable(name="parent_operation") as parent:
        # Create child operations
        async def child_operation(child_id: int):
            child = Cancellable(
                name=f"child_{child_id}",
                parent=parent
            )

            async with child:
                # Child will be cancelled if parent is cancelled
                await do_child_work()

        # Run children
        async with anyio.create_task_group() as tg:
            for i in range(5):
                tg.start_soon(child_operation, i)
```

## Pattern: Conditional Cancellation

Cancel based on system resources:

```python
import psutil

def check_memory_usage():
    """Cancel if memory usage is too high."""
    return psutil.virtual_memory().percent > 90

async def memory_aware_operation():
    async with Cancellable.with_condition(
        check_memory_usage,
        check_interval=5.0,
        condition_name="memory_check"
    ) as cancel:
        cancel.on_cancel(
            lambda ctx: logger.warning("Operation cancelled due to high memory usage")
        )

        await memory_intensive_operation()
```

## Pattern: Stream Processing with Backpressure

Handle backpressure in stream processing:

```python
async def process_stream_with_backpressure(source: AsyncIterator[Any]):
    # Create bounded channel for backpressure
    send_channel, receive_channel = anyio.create_memory_object_stream(max_buffer_size=100)

    async with Cancellable(name="stream_processing") as cancel:
        async def producer():
            async with send_channel:
                async for item in cancel.stream(source):
                    try:
                        # Try to send without blocking
                        send_channel.send_nowait(item)
                    except anyio.WouldBlock:
                        # Handle backpressure
                        await cancel.report_progress(
                            "Backpressure detected, waiting for consumer"
                        )
                        await send_channel.send(item)

        async def consumer():
            async with receive_channel:
                async for item in receive_channel:
                    # Process item
                    await process_item(item)

        # Run producer and consumer concurrently
        async with anyio.create_task_group() as tg:
            tg.start_soon(producer)
            tg.start_soon(consumer)
```

## Anti-Patterns to Avoid

### Don't forget to check cancellation in loops

❌ **Bad:**
```python
async with Cancellable.with_timeout(10) as cancel:
    for item in large_list:
        # This might run forever if list is large
        await process_item(item)
```

✅ **Good:**
```python
async with Cancellable.with_timeout(10) as cancel:
    for item in large_list:
        # Check cancellation in each iteration
        await cancel._token.check_async()
        await process_item(item)
```

### Don't ignore cancellation in cleanup

❌ **Bad:**
```python
try:
    async with Cancellable.with_timeout(10) as cancel:
        result = await operation()
finally:
    # This might not run if cancelled
    await cleanup()
```

✅ **Good:**
```python
async with Cancellable.with_timeout(10) as cancel:
    try:
        result = await operation()
    finally:
        # Shield cleanup from cancellation
        async with cancel.shield():
            await cleanup()
```

### Don't create unnecessary cancellables

❌ **Bad:**
```python
# Creating new cancellable for each item
for item in items:
    async with Cancellable() as cancel:
        await process_item(item)
```

✅ **Good:**
```python
# Reuse single cancellable
async with Cancellable() as cancel:
    for item in items:
        await process_item(item)
```
