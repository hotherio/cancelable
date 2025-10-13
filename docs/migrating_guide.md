# Migration Guide

## Migrating from asyncio.timeout

If you're currently using `asyncio.timeout` (Python 3.11+):

### Before:
```python
import asyncio

async with asyncio.timeout(30):
    result = await long_operation()
```

### After:
```python
from hother.cancelable import Cancellable

async with Cancellable.with_timeout(30) as cancel:
    result = await long_operation()
```

### Benefits:
- Progress reporting
- Multiple cancellation sources
- Better error handling
- Operation tracking

## Migrating from anyio.CancelScope

If you're using anyio's cancel scopes directly:

### Before:
```python
import anyio

with anyio.CancelScope() as scope:
    scope.deadline = anyio.current_time() + 30
    await operation()
```

### After:
```python
from hother.cancelable import Cancellable

async with Cancellable.with_timeout(30) as cancel:
    await operation()
```

### Benefits:
- Higher-level API
- Built-in progress tracking
- Automatic cleanup
- Integration with other libraries

## Migrating Manual Cancellation

If you have manual cancellation patterns:

### Before:
```python
class Worker:
    def __init__(self):
        self.should_stop = False

    async def run(self):
        while not self.should_stop:
            await self.do_work()

    def stop(self):
        self.should_stop = True
```

### After:
```python
from forge.async_cancellation import CancellationToken

class Worker:
    def __init__(self):
        self.token = CancellationToken()

    async def run(self):
        while True:
            await self.token.check_async()
            await self.do_work()

    async def stop(self):
        await self.token.cancel()
```

### Benefits:
- Thread-safe cancellation
- Proper async/await support
- Cancellation callbacks
- Integration with Cancellable

## Migrating Stream Processing

If you have custom stream cancellation:

### Before:
```python
async def process_stream(stream):
    try:
        async for item in stream:
            if should_stop():
                break
            await process_item(item)
    except asyncio.CancelledError:
        # Handle cancellation
        pass
```

### After:
```python
from hother.cancelable import Cancellable

async def process_stream(stream):
    async with Cancellable() as cancel:
        async for item in cancel.stream(stream):
            await process_item(item)
```

### Benefits:
- Automatic cancellation propagation
- Progress reporting
- Partial result preservation
- Clean error handling

## Adding to Existing Code

You can gradually adopt the cancellation system:

### Step 1: Add to Critical Operations
Start with operations that need timeouts:

```python
# Before
result = await critical_operation()

# After
from forge.async_cancellation import with_timeout
result = await with_timeout(30.0, critical_operation())
```

### Step 2: Add Progress Reporting
Enhance long-running operations:

```python
from forge.async_cancellation import cancellable

@cancellable(timeout=300)
async def process_data(data: list, cancellable=None):
    for i, item in enumerate(data):
        await process_item(item)
        if i % 100 == 0:
            await cancellable.report_progress(f"Processed {i} items")
```

### Step 3: Integrate with Your Framework
For web applications:

```python
# FastAPI example
from forge.async_cancellation.integrations.fastapi import cancellable_dependency

@app.post("/process")
async def process_endpoint(
    data: List[str],
    cancel: Cancellable = Depends(cancellable_dependency)
):
    async with cancel:
        return await process_data(data)
```

## Common Gotchas

### 1. Context Manager Scope
Remember that cancellation is scoped to the context manager:

```python
# ❌ Wrong: cancellable out of scope
cancel = Cancellable()
await operation()  # Not cancellable!

# ✅ Correct: use context manager
async with Cancellable() as cancel:
    await operation()  # Cancellable
```

### 2. Shielding Side Effects
Be careful with shielding:

```python
# ❌ Wrong: entire operation shielded
async with cancel.shield():
    await long_operation()  # Won't be cancelled!

# ✅ Correct: shield only critical parts
await long_operation()
async with cancel.shield():
    await critical_cleanup()  # Protected from cancellation
```

### 3. Token Lifecycle
Tokens can be reused but not reset:

```python
token = CancellationToken()

# First use
async with Cancellable.with_token(token):
    await operation1()

# Token can be cancelled later
await token.cancel()

# ❌ Wrong: token is already cancelled
async with Cancellable.with_token(token):
    await operation2()  # Will be immediately cancelled!

# ✅ Correct: create new token
new_token = CancellationToken()
async with Cancellable.with_token(new_token):
    await operation2()
```

## Performance Considerations

The cancellation system adds minimal overhead:

- Context manager: ~10-50% overhead vs raw async
- Cancellation checks: <10μs per check
- Stream processing: <100% overhead vs direct iteration

For most applications, this overhead is negligible compared to I/O operations.

## Getting Help

- Check the [examples/](examples/) directory for complete examples
- Read the [API Reference](api_reference.md) for detailed documentation
- Review [Common Patterns](patterns.md) for best practices
