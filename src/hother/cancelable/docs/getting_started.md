# Getting Started with Async Cancellation

## Installation

The async cancellation system is part of the Forge framework. Ensure you have the required dependencies:

```bash
uv pip install anyio asyncer pydantic httpx
```

## Basic Concepts

### Cancellable Operations

A `Cancellable` provides a context for managing async operations that can be cancelled from various sources:

```python
from forge.async_cancellation import Cancellable

async with Cancellable() as cancel:
    # Your async operation here
    result = await some_async_operation()
```

### Cancellation Sources

Operations can be cancelled from multiple sources:

1. **Timeout**: Cancel after a specified duration
2. **Token**: Manual cancellation via a token
3. **Signal**: OS signal handling (SIGINT, etc.)
4. **Condition**: Custom condition checking

## Quick Examples

### Timeout Cancellation

```python
from forge.async_cancellation import Cancellable
from datetime import timedelta

# Using seconds
async with Cancellable.with_timeout(30.0) as cancel:
    result = await long_running_operation()

# Using timedelta
async with Cancellable.with_timeout(timedelta(minutes=5)) as cancel:
    result = await very_long_operation()
```

### Manual Cancellation

```python
from forge.async_cancellation import Cancellable, CancellationToken

# Create a token
token = CancellationToken()

# In your async operation
async def my_operation():
    async with Cancellable.with_token(token) as cancel:
        # This will be cancelled when token.cancel() is called
        await some_work()

# Cancel from elsewhere
await token.cancel()
```

### Progress Reporting

```python
async with Cancellable() as cancel:
    # Register progress callback
    cancel.on_progress(lambda op_id, msg, meta: print(f"Progress: {msg}"))

    # Report progress during operation
    await cancel.report_progress("Starting operation")

    for i in range(100):
        await process_item(i)
        if i % 10 == 0:
            await cancel.report_progress(f"Processed {i} items", {"count": i})
```

### Stream Processing

```python
async with Cancellable.with_timeout(60) as cancel:
    # Process async stream with automatic cancellation
    async for item in cancel.stream(async_data_source()):
        await process_item(item)
```

## Best Practices

1. **Always use context managers**: Ensures proper cleanup
   ```python
   async with Cancellable() as cancel:
       # Your code here
   ```

2. **Report progress for long operations**: Helps with monitoring
   ```python
   await cancel.report_progress("Processing batch", {"size": len(batch)})
   ```

3. **Handle cancellation gracefully**: Save partial results
   ```python
   try:
       async with Cancellable.with_timeout(30) as cancel:
           result = await process_all()
   except Exception:
       # Save partial results from cancel.context.partial_result
       pass
   ```

4. **Use appropriate cancellation sources**: Choose based on your needs
   - Timeout: For operations with known maximum duration
   - Token: For user-initiated cancellation
   - Signal: For system-level interruption
   - Condition: For resource-based cancellation

## Next Steps

- Read the [API Reference](api_reference.md) for detailed documentation
- Check out [Common Patterns](patterns.md) for advanced usage
- See the `examples/` directory for complete examples
