# Advanced Usage

In addition to the basic cancelation mechanism, Cancelable offers some features to manage finely the context and monitor progress.

## Operation Context

The cancel context provides state and metadata that can be directly accessed:

```python
async with Cancelable.with_timeout(30.0, name="task") as cancel:
    # Context properties
    print(f"ID: {cancel.context.id}")  # (1)!
    print(f"Name: {cancel.context.name}")
    print(f"Status: {cancel.context.status}")  # (2)!
    print(f"Started: {cancel.context.start_time}")

    await operation()

# After completion
print(f"Reason: {cancel.context.cancel_reason}")  # (3)!
print(f"Message: {cancel.context.cancel_message}")
print(f"Elapsed: {cancel.context.elapsed_time}s")  # (4)!
```

1. Unique UUID for operation tracking and log correlation
2. Lifecycle: PENDING → RUNNING → CANCELLED or COMPLETED
3. Why it cancelled: TIMEOUT, MANUAL, SIGNAL, or CONDITION
4. Performance metrics available after completion

## Get current context with `current_operation()`

You can access the current `Cancelable` from anywhere without parameter passing:

```python
from hother.cancelable import Cancelable, current_operation

async def nested_function():
    """No explicit cancel parameter needed."""
    ctx = current_operation()  # (1)!
    if ctx:
        await ctx.report_progress("Working in nested function")  # (2)!
        print(f"Operation: {ctx.context.name}")

async def main():
    async with Cancelable.with_timeout(30.0, name="my_op") as cancel:
        await nested_function()  # (3)!
```

1. Retrieve current `Cancelable` from context vars - magic!
2. Full access to all features without explicit parameter
3. Clean function signatures - cancelation is implicit

!!! note "Context Variable Safety"
    `current_operation()` uses `contextvars.ContextVar`, which is automatically scoped to async contexts. Safe for concurrent operations.

## Hierarchical Operations

Create parent-child relationships for structured concurrency:

```python
async with Cancelable(name="parent") as parent:  # (1)!
    await parent_setup()

    # Child operations
    async with Cancelable(name="child_1", parent=parent) as child1:  # (2)!
        await child1_work()

    async with Cancelable(name="child_2", parent=parent) as child2:
        await child2_work()

    # (3)!
```

1. Parent operation defines the outer scope
2. Children link to parent via `parent` parameter
3. When parent cancels, **all** children cancel automatically (cascade)

**Benefits:**

- **Automatic propagation** - Parent cancelation cascades to all children
- **Clean hierarchy** - Track operation relationships in registry
- **Monitoring** - Visualize operation trees

### Nested Timeouts

Different timeout requirements for different steps:

```python
# Outer: 60-second total budget
async with Cancelable.with_timeout(60.0, name="outer") as outer:

    # Inner: 10-second timeout for quick step
    async with Cancelable.with_timeout(10.0, name="step1", parent=outer) as step1:
        await quick_operation()

    # Inner: 45-second timeout for slow step
    async with Cancelable.with_timeout(45.0, name="step2", parent=outer) as step2:
        await long_operation()

    # If outer times out, both steps cancel
    # If step times out, only that step cancels
```

## Progress Reporting

Track and report operation progress with callbacks:

```python
async with Cancelable(name="processor") as cancel:
    # Register progress callback
    def on_progress(operation_id: str, message: str, metadata: dict):  # (1)!
        print(f"[{operation_id}] {message}")
        progress_percent = metadata.get('progress', 0)
        print(f"Progress: {progress_percent}%")

    cancel.on_progress(on_progress)  # (2)!

    # Report progress during operation
    total = len(items)
    for i, item in enumerate(items):
        await process_item(item)

        if i % 100 == 0:  # (3)!
            await cancel.report_progress(  # (4)!
                f"Processed {i}/{total} items",
                {
                    "progress": (i / total) * 100,
                    "current": i,
                    "total": total
                }
            )
```

1. Callback receives operation ID, human-readable message, and structured metadata
2. Register callback to receive all progress updates
3. Report periodically to avoid performance overhead
4. Include both message and metadata for flexible consumption (UIs, logs, metrics)

### Multiple Callbacks

Register different callbacks for different purposes:

```python
async with Cancelable(name="processor") as cancel:
    # UI callback
    def update_ui(op_id, msg, meta):
        progress_bar.update(meta.get('progress', 0))
        status_label.set_text(msg)

    # Logging callback
    def log_progress(op_id, msg, meta):
        logger.info(f"Operation {op_id}: {msg}", extra=meta)

    # Metrics callback
    def update_metrics(op_id, msg, meta):
        metrics.gauge('operation.progress', meta.get('progress', 0))

    # Register all
    cancel.on_progress(update_ui)
    cancel.on_progress(log_progress)
    cancel.on_progress(update_metrics)

    await process_data()
```

### Progress in Hierarchies

Progress reports bubble up through the hierarchy:

```python
async with Cancelable(name="pipeline") as pipeline:
    def pipeline_progress(op_id, msg, meta):
        print(f"Pipeline: {msg}")

    pipeline.on_progress(pipeline_progress)  # (1)!

    async with Cancelable(name="step1", parent=pipeline) as step1:
        step1.on_progress(lambda oid, m, meta: print(f"  Step1: {m}"))
        await step1.report_progress("Starting step 1")  # (2)!
        await work()

    async with Cancelable(name="step2", parent=pipeline) as step2:
        step2.on_progress(lambda oid, m, meta: print(f"  Step2: {m}"))
        await step2.report_progress("Starting step 2")  # (3)!
        await work()
```

1. Pipeline callback receives progress from all children
2. Step 1 reports to its own callback and bubbles to pipeline callback
3. Step 2 reports to its own callback and bubbles to pipeline callback

### Metadata Structure

Use consistent metadata structure for better tooling:

```python
# Standard fields
metadata = {
    "progress": 65.5,        # Percentage (0-100)
    "current": 655,          # Current item number
    "total": 1000,           # Total items
    "rate": 12.5,            # Items per second
    "eta": 27.6,             # Estimated seconds remaining
    "phase": "processing"    # Current phase name
}

await cancel.report_progress("Processing batch 7/10", metadata)
```

### Async Progress Reporting

Progress reporting is async to allow for async callbacks:

```python
async def async_progress_handler(op_id, msg, meta):
    """Callback can be async for database/API updates."""
    await db.update_job_progress(op_id, meta['progress'])
    await metrics_api.send(op_id, meta)

async with Cancelable(name="job") as cancel:
    cancel.on_progress(async_progress_handler)  # (1)!
    await process_job()
```

1. Async callbacks are awaited automatically

### Performance Tips

**✅ Do:**

- Report at milestones (every 100-1000 items)
- Use lightweight callbacks
- Include structured metadata for flexibility
- Report less frequently for high-throughput operations

**❌ Don't:**

- Report on every iteration (huge overhead)
- Do expensive work in callbacks (blocks operation)
- Report more than once per second for UI updates
- Forget to include context in metadata

### Example: Web UI Progress

```python
from fastapi import WebSocket

@app.websocket("/progress/{job_id}")
async def progress_websocket(websocket: WebSocket, job_id: str):
    await websocket.accept()

    async def send_progress(op_id, msg, meta):
        """Send progress updates to WebSocket client."""
        await websocket.send_json({
            "operation_id": op_id,
            "message": msg,
            "metadata": meta
        })

    async with Cancelable(name=f"job_{job_id}") as cancel:
        cancel.on_progress(send_progress)

        for i, item in enumerate(items):
            await process_item(item)

            if i % 10 == 0:  # Update UI every 10 items
                await cancel.report_progress(
                    f"Processing item {i}/{len(items)}",
                    {
                        "progress": (i / len(items)) * 100,
                        "current": i,
                        "total": len(items)
                    }
                )
```

### Combining Hierarchies and Progress

Use together for comprehensive operation monitoring:

```python
async with Cancelable(name="workflow") as workflow:
    workflow.on_progress(lambda oid, m, meta: logger.info(f"Workflow: {m}"))

    async with Cancelable(name="stage1", parent=workflow) as stage1:
        stage1.on_progress(lambda oid, m, meta: print(f"  Stage 1: {m}"))

        for i in range(100):
            await work()
            if i % 10 == 0:
                await stage1.report_progress(
                    f"Stage 1: {i}/100",
                    {"progress": i, "stage": "fetch"}
                )

    async with Cancelable(name="stage2", parent=workflow) as stage2:
        stage2.on_progress(lambda oid, m, meta: print(f"  Stage 2: {m}"))

        for i in range(200):
            await work()
            if i % 20 == 0:
                await stage2.report_progress(
                    f"Stage 2: {i}/200",
                    {"progress": i, "stage": "process"}
                )
```

## Custom Combining Patterns

### OR vs AND Logic for Source Combining

Cancelable supports two ways to combine cancellation sources:

| Logic | When Cancels | Use Case | Implementation |
|-------|--------------|----------|----------------|
| **OR (any-of)** | When **ANY** source triggers | Safety nets, failsafes | `Cancelable.combine()`, `CompositeSource`, or `AnyOfSource` |
| **AND (all-of)** | When **ALL** sources trigger | Requirements, conditions | `AllOfSource` |

### AND Logic (All-Of) - Require Multiple Conditions

Use `AllOfSource` when ALL conditions must be met before cancelling:

```python
from hother.cancelable import Cancelable
from hother.cancelable.sources.composite import AllOfSource
from hother.cancelable.sources.timeout import TimeoutSource
from hother.cancelable.sources.condition import ConditionSource

# Example: Batch job that needs BOTH minimum time AND target count
items_processed = 0
start_time = time.time()

min_time_source = TimeoutSource(timeout=60.0)  # (1)!
target_reached_source = ConditionSource(
    condition=lambda: items_processed >= 1000,  # (2)!
    check_interval=1.0
)

# Combine with AND logic
all_of = AllOfSource([min_time_source, target_reached_source])  # (3)!

cancelable = Cancelable(name="batch_job")
cancelable.add_source(all_of)

async with cancelable:
    for item in items:
        await process_item(item)
        items_processed += 1
        # Continues until BOTH 60s passed AND 1000 items processed
```

1. First requirement: minimum 60 seconds must pass
2. Second requirement: must process at least 1000 items
3. `AllOfSource` ensures BOTH conditions are met before cancelling

### Practical Use Cases for AND Logic

#### 1. Rate-Limited Operations with Minimum Duration

```python
# Process at least 100 items AND respect 30-second minimum
min_items = ConditionSource(
    condition=lambda: processed_count >= 100,
    check_interval=0.5
)
min_time = TimeoutSource(timeout=30.0)

all_of = AllOfSource([min_items, min_time])
# Ensures quality (minimum items) AND prevents too-fast completion
```

#### 2. Resource-Ready AND Quota-Available

```python
# Wait until BOTH disk space available AND API quota refreshed
disk_available = ConditionSource(
    condition=lambda: shutil.disk_usage("/").free > 1_000_000_000,  # 1GB
    check_interval=5.0
)
quota_available = ConditionSource(
    condition=lambda: api_quota_remaining > 100,
    check_interval=10.0
)

all_of = AllOfSource([disk_available, quota_available])
# Only proceeds when both resources are ready
```

#### 3. Multi-Stage Completion Gates

```python
# All stages must signal completion
stage1_complete = ConditionSource(condition=lambda: stage1_done, check_interval=1.0)
stage2_complete = ConditionSource(condition=lambda: stage2_done, check_interval=1.0)
stage3_complete = ConditionSource(condition=lambda: stage3_done, check_interval=1.0)

all_of = AllOfSource([stage1_complete, stage2_complete, stage3_complete])
# Pipeline completes only when all stages finish
```

### Thread Safety

`AllOfSource` is thread-safe using `anyio.Lock()` for tracking triggered sources:

```python
async def _monitor_source(self, source: CancelationSource) -> None:
    """Monitor a single source and check if all have triggered."""
    original_trigger = source.trigger_cancelation

    async def wrapped_trigger(message: str | None = None):
        async with self._lock:  # Thread-safe
            self.triggered_sources.add(source)

            # Check if all sources have triggered
            if len(self.triggered_sources) == len(self.sources):
                await self.trigger_cancelation(
                    f"All {len(self.sources)} sources have triggered"
                )
```

Safe for concurrent source triggering from multiple tasks or threads.

### Combining OR and AND Logic

Nest `AllOfSource` within `CompositeSource` or `AnyOfSource` for complex logic:

```python
from hother.cancelable import AnyOfSource, AllOfSource

# Complex: (Timeout OR Signal) OR (MinTime AND TargetReached)
safety_net = AnyOfSource([  # OR logic (AnyOfSource is an alias for CompositeSource)
    TimeoutSource(timeout=300.0),  # 5-minute hard timeout
    SignalSource(signal.SIGTERM),  # Or graceful shutdown
])

completion_requirements = AllOfSource([  # AND logic
    TimeoutSource(timeout=60.0),  # Minimum 60 seconds
    ConditionSource(lambda: items >= 1000, 1.0),  # AND 1000 items
])

# Combine both (OR of two groups)
final = AnyOfSource([safety_net, completion_requirements])
# Cancels on: hard timeout OR signal OR (minimum time AND target count)
```

!!! tip "Semantic Clarity with AnyOfSource"
    `AnyOfSource` is an alias for `CompositeSource` that makes the intent clearer when contrasting with `AllOfSource`. Use whichever name makes your code more readable.

### Best Practices

**✅ Do:**

- Use AND logic for quality gates (minimum time, minimum items)
- Use AND logic for resource synchronization (all resources ready)
- Keep check intervals reasonable (1-10 seconds)
- Document why all conditions are required

**❌ Don't:**

- Use AND logic for safety timeouts (use OR instead)
- Combine too many conditions (> 4-5 gets complex)
- Use very short check intervals (< 0.1s) on conditions
- Forget that ALL conditions must eventually trigger (or operation never cancels)

## Decorators

Instead of manually creating `Cancelable` contexts with `async with`, decorators:

- **Simplify code** - Reduce boilerplate for common cancelation patterns
- **Inject context** - Automatically provide `Cancelable` instances as parameters
- **Compose sources** - Combine multiple cancelation triggers
- **Share contexts** - Coordinate cancelation across multiple functions

### @cancelable vs @with_cancelable

Two decorator styles for different needs:

| Feature | `@cancelable` | `@with_cancelable` |
|---------|--------------|-------------------|
| **Context Creation** | ✅ Creates new for each call | ❌ Uses existing instance |
| **Context Management** | ✅ Auto `async with` | ❌ Manual `async with` required |
| **Timeout Configuration** | ✅ Per decorator params | ❌ Pre-configured |
| **Context Sharing** | ❌ Independent per call | ✅ Shared across functions |
| **Default Injection** | ✅ Yes (`inject_param`) | ❌ No (`inject=False`) |
| **Use Case** | Individual operations | Coordinated workflows |

**`@cancelable` - Independent Contexts**

Each call gets its own timeout:

```python
from hother.cancelable import cancelable

@cancelable(timeout=5.0, name="process_item")  # (1)!
async def process_item(item: str, cancelable: Cancelable):
    await cancelable.report_progress(f"Processing {item}")
    await do_work(item)
    return f"Done: {item}"

# Each call is independent
await process_item("A")  # ✓ Fresh 5s timeout
await process_item("B")  # ✓ Fresh 5s timeout
await process_item("C")  # ✓ Fresh 5s timeout
# Total time can exceed 5 seconds
```

1. Decorator creates and manages context automatically

**`@with_cancelable` - Shared Context**

All calls share one timeout:

```python
from hother.cancelable import Cancelable, with_cancelable, current_operation

# Create ONE shared context
batch_cancel = Cancelable.with_timeout(5.0, name="batch")  # (1)!

@with_cancelable(batch_cancel)  # (2)!
async def process_item(item: str):
    ctx = current_operation()  # (3)!
    await ctx.report_progress(f"Processing {item}")
    await do_work(item)
    return f"Done: {item}"

# All share the same 5-second budget
async with batch_cancel:  # (4)!
    await process_item("A")
    await process_item("B")
    await process_item("C")
    # Total time for ALL items must be < 5 seconds
```

1. One cancelable instance shared across multiple functions
2. Decorator wraps function with existing instance
3. Access via `current_operation()` - no parameter injection by default
4. Manual context entry required with `async with`

### All Decorator Variants

**`@cancelable` - Basic Timeout**

```python
@cancelable(timeout=30.0, name="fetch_data")
async def fetch_data(url: str, cancelable: Cancelable):
    return await http_client.get(url)
```

**`@cancelable_with_token` - Manual Control**

```python
token = CancelationToken()

@cancelable_with_token(token, name="worker")
async def background_worker(data: list, cancelable: Cancelable):
    for item in data:
        await process_item(item)
```

**`@cancelable_with_signal` - Graceful Shutdown**

```python
@cancelable_with_signal(signal.SIGTERM, signal.SIGINT, name="service")
async def long_running_service(cancelable: Cancelable):
    while True:
        await process_batch()
        await anyio.sleep(1)
```

**`@cancelable_with_condition` - Custom Logic**

```python
def check_memory():
    return psutil.virtual_memory().percent > 90

@cancelable_with_condition(check_memory, check_interval=5.0)
async def memory_intensive_task(data: list, cancelable: Cancelable):
    return await process_large_dataset(data)
```

**`@cancelable_combine` - Multiple Sources**

```python
@cancelable_combine(
    Cancelable.with_timeout(300.0),
    Cancelable.with_token(token),
    Cancelable.with_signal(signal.SIGTERM),
    name="robust_operation"
)
async def download_file(url: str, cancelable: Cancelable):
    return await download(url)
```

### Parameter Injection

By default, decorators inject the `Cancelable` instance as a parameter:

```python
@cancelable(timeout=30.0)
async def my_function(arg1, arg2, cancelable: Cancelable):  # (1)!
    await cancelable.report_progress("Working...")
    return await do_work(arg1, arg2)
```

1. `cancelable` parameter is automatically injected

Even without injection, it is possible to access the `Cancelable` via `current_operation()` instead:

```python
from hother.cancelable import cancelable, current_operation

@cancelable(timeout=30.0, inject_param=None)  # (1)!
async def clean_signature(arg1, arg2):  # (2)!
    ctx = current_operation()  # (3)!
    if ctx:
        await ctx.report_progress("Working...")
    return await do_work(arg1, arg2)
```

1. Set `inject_param=None` to disable injection
2. Clean function signature without cancelable parameter
3. Access context via `current_operation()` when needed

You can use a custom parameter name for the injection:

```python
@cancelable(timeout=30.0, inject_param="cancel")
async def my_function(arg1, cancel=None):  # Uses 'cancel' instead
    await cancel.report_progress("Working...")
```

### Decision Guide

**Choose `@cancelable` when:**

- Each call needs its own independent timeout
- You want declarative cancelation at function level
- Functions should be self-contained
- Example: API endpoints, isolated tasks

**Choose `@with_cancelable` when:**

- Multiple functions share one timeout/cancelation state
- You want cleaner function signatures
- Building coordinated workflows/pipelines
- Example: Request-scoped operations, batch jobs

### Additional Decorators

**`@cancelable_method` - For Class Methods**

Decorator for class methods with automatic operation naming:

```python
from hother.cancelable import cancelable_method

class DataProcessor:
    @cancelable_method(timeout=30.0)
    async def process(self, data, cancelable: Cancelable):
        # Operation name automatically includes class name
        # e.g., "DataProcessor.process"
        await cancelable.report_progress("Processing...")
        return await heavy_computation(data)

processor = DataProcessor()
result = await processor.process(data)
# Each instance method call gets its own 30s timeout
```

**Benefits**:
- Automatic naming: `ClassName.method_name`
- Works with instance and class methods
- Same features as `@cancelable`

**`@with_current_operation` - Inject Current Context**

Inject current operation without creating new context:

```python
from hother.cancelable.utils.decorators import with_current_operation

@with_current_operation()
async def helper_function(data, operation=None):
    # Gets current operation from context
    if operation:
        await operation.report_progress(f"Processing {data}")
    return await work(data)

async with Cancelable.with_timeout(30.0) as cancel:
    # helper_function automatically gets current operation
    result = await helper_function("data")
```

**Use cases**:
- Utility functions that need operation context
- Avoiding explicit parameter passing
- Clean function signatures

## Wrapping Operations

The `wrap()` method provides automatic cancelation checking for operations, especially useful in retry loops and batch processing where you want clean cancelation semantics without explicit checks.

### Using `wrap()`

Wrap a callable to automatically check for cancelation before each execution:

```python
async with Cancelable.with_timeout(30.0, name="retry_operation") as cancel:  # (1)!
    wrapped_fetch = cancel.wrap(fetch_data)  # (2)!

    # Retry loop - checks cancelation before each attempt
    for attempt in range(3):  # (3)!
        try:
            result = await wrapped_fetch(url)
            break
        except Exception as e:
            if attempt < 2:  # Don't sleep on last attempt
                await anyio.sleep(1)
```

1. Create cancelable context with timeout
2. Wrap the operation once - returns a callable that checks cancelation
3. Each call automatically checks all cancelation sources before executing

**How it works:**

- `wrap()` returns a new callable that wraps your original function
- Before each call, it checks if any cancelation source has triggered
- If cancelled, raises `CancelledError` immediately
- If not cancelled, executes your original function normally

### Using `wrapping()` Context Manager

For scoped wrapping operations with cleaner syntax:

```python
async with Cancelable.with_timeout(30.0) as cancel:
    async with cancel.wrapping() as wrap:  # (1)!
        result = await wrap(operation)  # (2)!
        another = await wrap(another_operation)
```

1. Context manager that provides wrapping function in scope
2. Clean scoped access - wrap multiple operations without storing references

### When to Use Wrapping

**Use `wrap()` for:**

- **Retry loops**: Automatic cancelation between retry attempts
- **Batch processing**: Check cancelation for each item without manual checks
- **Integration with retry libraries**: Works seamlessly with Tenacity, backoff, etc.
- **Long-running loops**: Clean cancelation in `for` or `while` loops

**Example: Batch Processing**

```python
async with Cancelable.with_timeout(60.0, name="batch") as cancel:
    wrapped_process = cancel.wrap(process_item)  # (1)!

    for item in large_dataset:  # (2)!
        # Cancelation checked automatically
        result = await wrapped_process(item)
        results.append(result)
```

1. Wrap once outside the loop
2. Each iteration checks cancelation first - clean early exit on timeout

**Example: Retry with Tenacity**

```python
from tenacity import AsyncRetrying, stop_after_attempt

async with Cancelable.with_timeout(60.0, name="fetch") as cancel:
    wrapped_fetch = cancel.wrap(fetch_data)  # (1)!

    async for attempt in AsyncRetrying(stop=stop_after_attempt(3)):  # (2)!
        with attempt:
            result = await wrapped_fetch(url)
            return result
```

1. Wrap function to respect cancelation during retries
2. Retries up to 3 times, but stops immediately if cancelled (timeout, manual, etc.)

## Advanced Token Features

### LinkedCancelationToken

Advanced token with chaining and reason propagation:

```python
from hother.cancelable import CancelationToken
from hother.cancelable.core.token import LinkedCancelationToken

# Create linked token
parent_token = CancelationToken()
child_token = LinkedCancelationToken()

# Link child to parent - child cancels when parent cancels
child_token.link(parent_token)

# Cancel parent - child is automatically cancelled
await parent_token.cancel("Parent cancelled")

# Check child - it's cancelled too with reason propagated
assert child_token.is_cancelled
print(child_token.cancel_message)  # "Linked from parent: Parent cancelled"
```

**Use cases**:
- Building token hierarchies
- Propagating cancelation through pipelines
- Preserving cancelation reasons across boundaries

### Token Callbacks

Register async callbacks triggered on cancelation:

```python
token = CancelationToken()

# Register callback
async def on_cancel(message: str):
    print(f"Cancelled: {message}")
    await cleanup_resources()
    await notify_users()

token.register_callback(on_cancel)

# Later: cancel triggers callback
await token.cancel("Timeout reached")  # Calls on_cancel("Timeout reached")
```

**Use cases**:
- Custom cleanup logic
- Notification systems
- Logging and metrics
- Integration with external systems

### Token Checking Methods

Two different check methods with different exception types:

```python
token = CancelationToken()

# check() - raises ManualCancelation (custom exception)
try:
    token.check()
except ManualCancelation as e:
    print(f"Cancelled: {e.message}")

# check_async() - raises anyio.CancelledError (anyio exception)
try:
    await token.check_async()
except anyio.get_cancelled_exc_class():
    print("Cancelled")
```

**When to use**:
- `check()` - When you want to catch cancelation separately from other async cancelations
- `check_async()` - When you want cancelation to bubble up like normal async cancelation

## Partial Results

### OperationContext.partial_result

Store intermediate results that can be retrieved even if operation is cancelled:

```python
async with Cancelable.with_timeout(60.0) as cancel:
    results = []

    for i, item in enumerate(large_dataset):
        result = await process_item(item)
        results.append(result)

        # Store partial results periodically
        if i % 100 == 0:
            cancel.context.partial_result = {
                "processed": i,
                "results": results[:],
                "progress": i / len(large_dataset)
            }

    return results

# If cancelled, retrieve partial results
try:
    final = await process_dataset()
except anyio.get_cancelled_exc_class():
    # Get what we processed before cancelation
    partial = cancel.context.partial_result
    print(f"Processed {partial['processed']} items before cancel")
    return partial['results']
```

**Use cases**:
- Long-running batch jobs
- Data processing pipelines
- Resumable operations
- Progress checkpointing
