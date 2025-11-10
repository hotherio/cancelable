# Threading & Cross-Context Cancelation

Cancel async operations from threads and bridge between sync/async worlds.

## Overview

**Cross-thread cancelation** is a core feature that allows you to cancel async operations from synchronous code or different threads. This solves the fundamental problem of coordinating between Python's threading and async ecosystems.

Cancelable solves this with thread-safe cancelation:

```python
token = CancelationToken()

def button_click_handler():  # Runs in GUI thread
    token.cancel_sync("User clicked cancel")  # Thread-safe!

async def long_async_operation():
    async with Cancelable.with_token(token) as cancel:
        await process_data()  # Respects cancelation from thread
```

## Thread-Safe Cancelation

Cancel async operations from synchronous threads:

```python
import threading
import time
from hother.cancelable import CancelationToken, Cancelable

token = CancelationToken()

async def async_worker():
    """Long-running async operation."""
    async with Cancelable.with_token(token, name="worker") as cancel:
        for i in range(100):
            await process_item(i)
            await anyio.sleep(0.1)

def sync_canceller():
    """Runs in separate thread."""
    time.sleep(5)  # Wait 5 seconds
    # Thread-safe cancelation
    token.cancel_sync(message="Cancelled from thread")  # (1)!

# Start thread
thread = threading.Thread(target=sync_canceller)
thread.start()

# Run async work
await async_worker()  # Will be cancelled after 5 seconds
thread.join()
```

1. `cancel_sync()` is thread-safe and works from any thread

## Thread-Safe Registry Operations

### ThreadSafeRegistry

Synchronous API for the operation registry, designed for thread-based web frameworks (Flask, Django).

**Why you need this**: `OperationRegistry` is async by default, but many Python web frameworks run in synchronous threads.

```python
from hother.cancelable.utils.threading_bridge import ThreadSafeRegistry

# In Flask/Django view
registry = ThreadSafeRegistry()

# Cancel an operation from a synchronous endpoint
@app.post("/jobs/<job_id>/cancel")
def cancel_job(job_id):
    registry.cancel_operation(job_id, "User requested cancel")
    return {"status": "cancelled"}

# Get statistics synchronously
@app.get("/stats")
def get_stats():
    stats = registry.get_statistics()
    return {
        "total": stats.total_operations,
        "running": stats.running_operations,
        "cancelled": stats.cancelled_operations
    }

# Cancel all operations matching a pattern
@app.post("/jobs/cancel-all")
def cancel_all_user_jobs(user_id):
    registry.cancel_all(name_pattern=f"user_{user_id}_*")
    return {"status": "all_cancelled"}
```

**Methods**:
- `cancel_operation(operation_id, reason)` - Cancel specific operation
- `cancel_all(name_pattern=None)` - Cancel all or filtered operations
- `get_statistics()` - Get registry statistics
- `get_operation(operation_id)` - Retrieve operation context

## Context Propagation to Threads

### ContextBridge

Propagate context variables (like `current_operation()`) to threads safely.

**The problem**: Python's `contextvars` don't automatically propagate to threads, so `current_operation()` returns `None` in threads.

**The solution**:

```python
from hother.cancelable.utils.context_bridge import ContextBridge

async def main():
    async with Cancelable.with_timeout(30.0, name="parent") as cancel:
        # Run blocking operation in thread with context preserved
        bridge = ContextBridge()

        def sync_work():
            # current_operation() works here!
            ctx = current_operation()
            print(f"Operation: {ctx.context.name}")  # Prints "parent"

        result = await bridge.run_in_thread_with_context(sync_work)
```

**Methods**:
- `run_in_thread_with_context(func, *args, **kwargs)` - Run function in thread with context
- `copy_context()` - Capture current context
- `restore_context(context)` - Restore captured context

## Running Blocking Operations in Threads

### run_in_thread() Method

Run synchronous functions in threads while preserving cancelation context.

```python
async with Cancelable.with_timeout(30.0) as cancel:
    # Run blocking I/O in thread
    def blocking_database_query():
        # Simulates blocking call that can't be async
        return database.execute_slow_query()

    result = await cancel.run_in_thread(blocking_database_query)
    # Respects cancelation even while running in thread
```

**Use case**: Integrating blocking libraries (database drivers, file operations) that don't have async support.

## Thread-to-Async Communication

### AnyioBridge

Thread-to-anyio communication bridge for high-throughput scenarios.

```python
from hother.cancelable.utils.anyio_bridge import AnyioBridge

bridge = AnyioBridge(buffer_size=1000)  # Configure buffer

async with bridge:
    # From another thread, send data to async code
    def thread_producer():
        for item in generate_data():
            bridge.call_soon_threadsafe(process_item, item)

    # Start thread
    thread = threading.Thread(target=thread_producer)
    thread.start()

    # Process in async context
    await process_all_items()
```

**Parameters**:
- `buffer_size` - Queue size for thread-to-async communication
- `max_workers` - Thread pool size

**Use cases**:
- High-throughput data ingestion
- Integrating synchronous libraries
- Thread pool management
