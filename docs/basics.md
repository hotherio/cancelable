# Basics

Cancelable evolves around `Cancelable` object and the different sources of cancelation. Most other features are convenience or syntactic sugar to enable more pythonic idioms.    
In this tutorial, you will learn the essential concepts to start using Cancelable in your async Python applications.

## What is Cancelable?

`Cancelable` is an async context manager that wraps your operations and provides clean, composable cancelation from multiple sources:

- **Timeouts** - Automatic cancelation after a duration
- **Manual tokens** - Programmatic cancelation from code or threads
- **OS signals** - Graceful shutdown (SIGTERM, SIGINT)
- **Custom conditions** - Resource limits, business logic triggers

Think of it as "structured cancelation" for async Python - similar to how `anyio` provides structured concurrency.

## Quick Start

The simplest pattern - timeout after 30 seconds:

```python
from hother.cancelable import Cancelable
import anyio

async def main():
    try:
        async with Cancelable.with_timeout(30.0, name="api_call") as cancel:  # (1)!
            result = await external_api.fetch_data()
            return result
    except anyio.get_cancelled_exc_class():  # (2)!
        print("Operation timed out after 30 seconds")
        return None

anyio.run(main)
```

1. Create a cancelable context with a 30-second timeout - operation cancels automatically if exceeded
2. Handle the cancelation exception using `anyio.get_cancelled_exc_class()` for backend-agnostic code

## Four Ways to Trigger Cancelation

### 1. Timeout - Time-Based Cancelation

Automatically cancel after a specific duration:

```python
from hother.cancelable import Cancelable

async with Cancelable.with_timeout(60.0, name="batch_job") as cancel:  # (1)!
    await process_large_batch()
```

1. Most common pattern for API calls, database queries, and any operation with an SLA

**When to use:**

- API calls with response time limits
- Database queries that shouldn't run too long
- Batch operations with processing windows
- Any operation that needs a deadline

### 2. Manual Token - Programmatic Control

Cancel from anywhere in your code, even from other tasks or threads:

```python
from hother.cancelable import Cancelable, CancelationToken

# Create a shared token
token = CancelationToken()  # (1)!

async def worker():
    async with Cancelable.with_token(token, name="worker") as cancel:  # (2)!
        for i in range(1000):
            await process_item(i)
            await anyio.sleep(0.1)

async def controller():
    """Cancel worker after 5 seconds."""
    await anyio.sleep(5)
    await token.cancel(message="Time's up!")  # (3)!

# Run both concurrently
async with anyio.create_task_group() as tg:
    tg.start_soon(worker)
    tg.start_soon(controller)
```

1. Token can be shared across tasks and even threads for coordination
2. Worker operation respects cancelation from the shared token
3. Controller triggers cancelation - worker stops immediately

**Thread-safe cancelation:**

```python
import threading
import time

def sync_canceller():
    """Cancel from a regular Python thread."""
    time.sleep(5)
    token.cancel_sync(message="Cancelled from thread")  # (1)!

thread = threading.Thread(target=sync_canceller)
thread.start()
await worker()  # Will be cancelled by the thread
thread.join()
```

1. `cancel_sync()` is thread-safe - safe to call from any thread

**When to use:**

- User-triggered cancelation (cancel buttons, close dialogs)
- Cross-task coordination (one task cancels another)
- API endpoints that stop background jobs
- Thread-to-async communication

### 3. OS Signals - Graceful Shutdown

Respond to termination signals for clean application shutdown:

```python
import signal
from hother.cancelable import Cancelable

async def main():
    async with Cancelable.with_signal(  # (1)!
        signal.SIGTERM,  # Graceful shutdown
        signal.SIGINT,   # Ctrl+C
        name="application"
    ) as cancel:
        try:
            print("Running... (Ctrl+C to stop)")
            await run_server()
        finally:
            # Shield cleanup from cancelation  # (2)!
            async with cancel.shield():
                print("Shutting down gracefully...")
                await cleanup_resources()
                print("Shutdown complete")

anyio.run(main)
```

1. Responds to SIGTERM (container orchestrators) and SIGINT (Ctrl+C)
2. Shield ensures cleanup code runs even during cancelation

!!! warning "Platform Compatibility"
    Signal handling works on **Unix-like systems** (Linux, macOS). Windows only supports `SIGINT` (Ctrl+C).

**When to use:**

- Production services needing graceful shutdown
- CLI tools responding to Ctrl+C
- Container/Docker lifecycle management
- Development servers (quick stop with Ctrl+C)

### 4. Custom Conditions - Resource Monitoring

Cancel based on custom logic - disk space, memory usage, business rules:

```python
import psutil
from hother.cancelable import Cancelable

def check_resources():
    """Cancel if memory usage exceeds 90%."""  # (1)!
    return psutil.virtual_memory().percent > 90

async with Cancelable.with_condition(  # (2)!
    predicate=check_resources,
    check_interval=5.0,  # Check every 5 seconds
    name="memory_intensive_task"
) as cancel:
    await process_large_dataset()
```

1. Custom predicate - returns True when cancelation should occur
2. Checks condition periodically - cancels immediately when True

!!! tip "Performance"
    Set `check_interval` appropriately: too frequent wastes CPU, too slow delays cancelation.

**When to use:**

- Resource monitoring (disk, memory, CPU limits)
- Business rule triggers (rate limits, quotas exceeded)
- External state checks (database flags, file existence)
- Stop flags for user-controlled operations

## Combining Multiple Sources

The power of Cancelable comes from composing multiple cancelation triggers. Use `Cancelable.combine()` to create operations that respond to timeouts, manual cancelation, signals, and custom conditions simultaneously.

**Key concept**: First-wins semantics - the operation cancels as soon as **any** source triggers.

```python
from hother.cancelable import Cancelable, CancelationToken
import signal

token = CancelationToken()

async with Cancelable.combine([  # (1)!
    Cancelable.with_timeout(60.0),               # 60-second timeout
    Cancelable.with_token(token),                # Manual cancel
    Cancelable.with_signal(signal.SIGTERM),      # Graceful shutdown
], name="multi_source_operation") as cancel:
    await operation()  # (2)!
```

1. `combine()` accepts a list of Cancelable instances with different sources
2. Cancels immediately when the first source triggers (timeout OR manual OR signal)

### OR vs AND Logic

By default, `combine()` uses **OR logic** (any-of) - cancels when **any** source triggers. For **AND logic** (all-of) where **all** sources must trigger, use `AllOfSource`:

**OR Logic (Default) - Cancel when ANY triggers:**

```python
# Cancels on FIRST trigger (timeout OR manual OR signal)
async with Cancelable.combine([
    Cancelable.with_timeout(60.0),
    Cancelable.with_token(token),
    Cancelable.with_signal(signal.SIGTERM),
]) as cancel:
    await operation()
```

**AND Logic - Cancel when ALL trigger:**

```python
from hother.cancelable import Cancelable
from hother.cancelable.sources.composite import AllOfSource
from hother.cancelable.sources.timeout import TimeoutSource
from hother.cancelable.sources.condition import ConditionSource

# Both conditions must be met
min_time = TimeoutSource(timeout=60.0)  # (1)!
data_ready = ConditionSource(
    condition=lambda: is_data_complete(),
    check_interval=1.0
)

all_of = AllOfSource([min_time, data_ready])  # (2)!

cancelable = Cancelable(name="requires_both")
cancelable.add_source(all_of)

async with cancelable:
    await process_data()  # (3)!
```

1. Minimum 60 seconds must pass
2. Wrap sources in `AllOfSource` for AND logic
3. Only cancels when BOTH timeout reached AND data is complete

**When to use each:**

- **OR (any-of)**: Safety nets - cancel on timeout OR user action OR signal (most common)
- **AND (all-of)**: Requirements - wait until minimum time AND target reached AND resources available

!!! tip "Advanced: Direct Source Composition"
    For more control, you can use `AnyOfSource` (for OR logic) and `AllOfSource` (for AND logic) directly instead of `Cancelable.combine()`:

    ```python
    from hother.cancelable import Cancelable, AnyOfSource
    from hother.cancelable.sources import TimeoutSource, SignalSource

    # Equivalent to Cancelable.combine() but with explicit control
    any_of = AnyOfSource([
        TimeoutSource(timeout=60.0),
        SignalSource(signal.SIGTERM),
    ])

    cancelable = Cancelable(name="my_operation")
    cancelable.add_source(any_of)

    async with cancelable:
        await operation()
    ```

    This approach is useful when you need to nest sources or create reusable source combinations. `AnyOfSource` is an alias for `CompositeSource` that provides semantic clarity when contrasting with `AllOfSource`. See [Advanced Usage](advanced.md#combining-or-and-and-logic) for complex nesting examples.

## Using Decorators

For cleaner code, it is possible to use the `@cancelable` decorator:

```python
from hother.cancelable import cancelable

@cancelable(timeout=30.0, name="fetch_user")  # (1)!
async def fetch_user(user_id: int, cancelable: Cancelable):  # (2)!
    """Fetch user with automatic 30-second timeout."""
    await cancelable.report_progress(f"Fetching user {user_id}")
    response = await api.get(f"/users/{user_id}")
    return response.json()

# Each call gets its own 30-second timeout
user1 = await fetch_user(123)  # (3)!
user2 = await fetch_user(456)
```

1. Decorator creates a new `Cancelable` context for each function call
2. `cancelable` parameter is auto-injected - access context features
3. No manual `async with` needed - decorator handles it

See [Advanced Usage](advanced.md#decorators) for all decorator variants.

## Error Handling

### Catching Cancelation

```python
import anyio
from hother.cancelable import CancelationReason

try:
    async with Cancelable.with_timeout(5.0) as cancel:
        result = await operation()
except anyio.get_cancelled_exc_class() as e:  # (1)!
    # Access cancel details
    reason = cancel.context.cancel_reason  # (2)!
    message = cancel.context.cancel_message

    print(f"Cancelled: {reason} - {message}")

    # Handle based on reason
    if reason == CancelationReason.TIMEOUT:  # (3)!
        print("Operation timed out - maybe retry?")
    elif reason == CancelationReason.MANUAL:
        print("User cancelled - don't retry")
```

1. Use `anyio.get_cancelled_exc_class()` for backend compatibility (asyncio, trio)
2. Context provides cancel reason and custom message for detailed error handling
3. Different reasons warrant different responses (retry timeouts, log manual cancels, etc.)

### Cleanup with Shielding

Protect critical cleanup code from cancelation:

```python
async with Cancelable.with_timeout(30.0) as cancel:
    try:
        await risky_operation()
    finally:
        # Shield ensures cleanup runs even if cancelled
        async with cancel.shield():  # (1)!
            await save_important_state()
            await close_connections()
```

1. Shielded section always completes - cancelation waits until done

!!! warning "Use Shields Sparingly"
    Shields prevent cancelation propagation. Overuse can lead to deadlocks or hung operations.

## Wrapping Operations

For retry loops or batch processing, use `wrap()` to check cancelation automatically:

```python
async with Cancelable.with_timeout(30.0) as cancel:
    wrapped_fetch = cancel.wrap(fetch_data)  # (1)!
    
    # Retry loop - automatic cancelation checking
    for attempt in range(3):
        try:
            result = await wrapped_fetch(url)  # (2)!
            break
        except Exception:
            await anyio.sleep(1)
```

1. Wrap the operation once - returns callable that checks cancelation
2. Each call automatically checks if cancelled before executing

See [Advanced Usage](advanced.md#wrapping-operations) for complete details on `wrap()` and `wrapping()` context manager.
