# Basic Patterns

Fundamental cancelation patterns for getting started.

_All examples on this page are complete and runnable. Find the source in [`examples/01_basics/`](https://github.com/hotherio/cancelable/tree/main/examples/01_basics)._

## Timeout Cancelation

Cancel operations that exceed a time limit.

### Simple Timeout

```python
--8<-- "01_basics/02_timeout_cancelation.py:example"
```

This example shows timeout-based cancelation with error handling.

**Run it:**
```bash
python examples/01_basics/02_timeout_cancelation.py
```

### Timeout with Cleanup

```python
async def with_cleanup():
    async with Cancelable.with_timeout(10.0) as cancel:
        try:
            await process_data()
        finally:
            # Shield cleanup from cancelation
            async with cancel.shield():
                await cleanup_resources()
```

## Manual Cancelation

Cancel operations programmatically using tokens.

### Basic Token Usage

Here's a complete example showing manual cancelation with tokens:

```python
--8<-- "01_basics/03_manual_cancelation.py:example"
```

**Run it:**
```bash
python examples/01_basics/03_manual_cancelation.py
```

### Thread-Safe Cancelation

Cancel from synchronous code or threads:

```python
import threading
import time
from hother.cancelable import CancelationToken

token = CancelationToken()

async def async_worker():
    async with Cancelable.with_token(token) as cancel:
        await long_async_operation()

def sync_canceller():
    """Runs in a separate thread."""
    time.sleep(5)
    # Thread-safe cancelation
    token.cancel_sync(message="Cancelled from thread")

# Start thread
thread = threading.Thread(target=sync_canceller)
thread.start()

# Run async work
await async_worker()
thread.join()
```

## Signal Handling

Cancel on OS signals for graceful shutdown.

### Graceful Shutdown

```python
import signal
from hother.cancelable import Cancelable

async def main():
    async with Cancelable.with_signal(
        signal.SIGTERM,  # Graceful shutdown
        signal.SIGINT,   # Ctrl+C
        name="application"
    ) as cancel:
        try:
            print("Application running... (Ctrl+C to stop)")
            await run_server()
        finally:
            # Always run cleanup
            async with cancel.shield():
                print("Shutting down gracefully...")
                await save_state()
                await close_connections()
                print("Shutdown complete")

anyio.run(main)
```

**Run it:**
```bash
python examples/02_advanced/08_signal_handling.py
# Press Ctrl+C to trigger graceful shutdown
```

!!! info "Platform Support"
    Signal handling works on Unix-like systems (Linux, macOS). Windows supports SIGINT (Ctrl+C) only.

## Condition-Based Cancelation

Cancel when custom conditions are met.

### Resource Monitoring

```python
import shutil
from hother.cancelable import ConditionSource, Cancelable

def disk_full():
    """Check if disk usage exceeds 95%."""
    usage = shutil.disk_usage("/")
    return (usage.used / usage.total) > 0.95

async def main():
    # Check disk every 5 seconds
    async with Cancelable(
        sources=[ConditionSource(
            predicate=disk_full,
            check_interval=5.0,
            description="Disk space monitor"
        )],
        name="file_processor"
    ) as cancel:
        await process_large_files()

anyio.run(main)
```

### Custom Business Logic

```python
class JobController:
    def __init__(self):
        self.should_stop = False

    def check_stop_flag(self):
        return self.should_stop

controller = JobController()

async def run_job():
    async with Cancelable(
        sources=[ConditionSource(
            predicate=controller.check_stop_flag,
            check_interval=1.0
        )],
        name="background_job"
    ) as cancel:
        await process_job()

# Stop job from API endpoint
@app.post("/jobs/stop")
async def stop_job():
    controller.should_stop = True
    return {"status": "stopping"}
```

**Run it:**
```bash
python examples/02_advanced/07_condition_cancelation.py
```

## Combined Cancelation

Compose multiple sources - cancels on FIRST trigger.

### Timeout + Manual + Signal

```python
--8<-- "02_advanced/01_combined_cancelation.py:example"
```

**Run it:**
```bash
python examples/02_advanced/01_combined_cancelation.py
```

### All Sources Combined

```python
from hother.cancelable import TimeoutSource, SignalSource, ConditionSource

async def comprehensive_example():
    token = CancelationToken()

    async with Cancelable.combine([
        TimeoutSource(600.0),                    # 10 min timeout
        SignalSource(signal.SIGTERM, signal.SIGINT),
        token,                                    # Manual
        ConditionSource(disk_full, 5.0)          # Disk space
    ], name="robust_operation") as cancel:
        # Cancels on FIRST trigger from ANY source
        await operation()
```

## Hierarchical Operations

Parent-child relationships with automatic propagation.

### Basic Hierarchy

```python
async def parent_task():
    async with Cancelable(name="parent") as parent:
        print("Parent started")

        # Child 1
        async with Cancelable(name="child_1", parent=parent) as child1:
            print("Child 1 working")
            await anyio.sleep(1)

        # Child 2
        async with Cancelable(name="child_2", parent=parent) as child2:
            print("Child 2 working")
            await anyio.sleep(1)

        # If parent cancels, ALL children auto-cancel!
        print("Parent complete")
```

### Timeout Propagation

```python
# Parent has 10s timeout
async with Cancelable.with_timeout(10.0, name="parent") as parent:

    # Children inherit cancelation (but can have their own)
    async with Cancelable(name="quick_task", parent=parent) as child1:
        await quick_operation()  # Must finish before parent timeout

    async with Cancelable(name="slow_task", parent=parent) as child2:
        await slow_operation()  # Cancelled if parent times out
```

## Decorated Functions

Apply cancelation to functions with decorators.

### Complete Example

The `@cancelable` decorator makes it easy to add cancelation to any function:

```python
--8<-- "01_basics/04_decorated_functions.py:example"
```

**Run it:**
```bash
python examples/01_basics/04_decorated_functions.py
```

## Best Practices

### ✅ Do

- **Name your operations** for better debugging
- **Handle cancelation exceptions** gracefully
- **Use shields** for critical cleanup
- **Combine sources** for robust cancelation
- **Start simple** - timeout only, then add more

### ❌ Don't

- **Don't ignore cancelation** - it indicates important state
- **Don't shield entire operations** - only cleanup sections
- **Don't use very short check intervals** (< 0.1s) for ConditionSource
- **Don't forget platform limits** for signal handling

## Common Patterns

### API Call with Timeout

```python
async def fetch_data(url: str):
    async with Cancelable.with_timeout(30.0, name=f"fetch_{url}") as cancel:
        response = await http_client.get(url)
        return response.json()
```

### Background Task with Cancel Button

```python
# Global token for UI cancel button
job_token = CancelationToken()

@app.post("/cancel")
async def cancel_job():
    await job_token.cancel("User clicked cancel")

async def background_job():
    async with Cancelable.with_token(job_token) as cancel:
        await process_job()
```

### CLI Tool with Ctrl+C

```python
import signal

async def cli_tool():
    async with Cancelable.with_signal(signal.SIGINT) as cancel:
        try:
            await process_files()
        finally:
            async with cancel.shield():
                await save_progress()
```

## Next Steps

- Explore [Stream Processing](streams.md) - Handle async streams
- Learn [Web Applications](web.md) - FastAPI integration
- Read [Core Concepts](../basics.md) - Understand the fundamentals
- Try [Advanced Patterns](../patterns.md) - Production patterns
