# Common Patterns and Best Practices

Here is a collection of common patterns that leverage `Cancelable`.

## Graceful Shutdown

Handle application shutdown gracefully:

```python
import signal
from hother.cancelable import Cancelable

async def main():
    # Handle SIGINT and SIGTERM
    async with Cancelable.with_signal(signal.SIGINT, signal.SIGTERM) as cancel:
        cancel.on_cancel(lambda ctx: print("Shutting down gracefully..."))

        # Your application logic
        await run_application()
```

Or using the decorator:

```python
import signal
from hother.cancelable import cancelable_with_signal

@cancelable_with_signal(signal.SIGINT, signal.SIGTERM)
async def main(cancelable=None):
    """Application with graceful shutdown."""
    cancelable.on_cancel(lambda ctx: print("Shutting down gracefully..."))
    await run_application()
```

## Resource Cleanup

Ensure resources are cleaned up even on cancelation:

```python
async def process_with_cleanup():
    resource = None

    async with Cancelable.with_timeout(30) as cancel:
        try:
            # Acquire resource
            resource = await acquire_resource()

            # Process
            result = await process(resource)

            return result

        finally:
            # Shield cleanup from cancelation
            if resource:
                async with cancel.shield():
                    await resource.cleanup()
```

## Batch Processing with Progress

Process data in batches with progress reporting:

```python
async def process_large_dataset(data: List[Any], batch_size: int = 100):
    async with Cancelable(name="batch_processing") as cancel:
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

## Retry with Cancelation

Implement retry logic with cancelation support:

```python
async def retry_with_cancelation(
    operation: Callable,
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
):
    async with Cancelable(name="retry_operation") as cancel:
        last_error = None

        # Wrap operation to automatically check cancelation
        wrapped_op = cancel.wrap(operation)

        for attempt in range(max_retries):
            try:
                # Cancelation checked automatically by wrap()
                result = await wrapped_op()
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

## Concurrent Operations with Shared Cancelation

Run multiple operations with shared cancelation:

```python
async def parallel_operations():
    async with Cancelable(name="parallel_work") as cancel:
        # Wrap process_item to automatically check cancelation
        wrapped_process = cancel.wrap(process_item)

        async def worker(worker_id: int, items: List[Any]):
            for item in items:
                # Cancelation checked automatically
                await wrapped_process(item)

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

## Hierarchical Cancelation

Create operation hierarchies with parent-child relationships:

```python
async def hierarchical_operations():
    async with Cancelable(name="parent_operation") as parent:
        # Create child operations
        async def child_operation(child_id: int):
            child = Cancelable(
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

## Conditional Cancelation

Cancel based on system resources:

```python
import psutil

def check_memory_usage():
    """Cancel if memory usage is too high."""
    return psutil.virtual_memory().percent > 90

async def memory_aware_operation():
    async with Cancelable.with_condition(
        check_memory_usage,
        check_interval=5.0,
        condition_name="memory_check"
    ) as cancel:
        cancel.on_cancel(
            lambda ctx: logger.warning("Operation cancelled due to high memory usage")
        )

        await memory_intensive_operation()
```
