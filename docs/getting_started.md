# Getting Started with Async Cancelation

!!! info "Installation"
    See the [Installation](installation.md) guide for complete installation instructions, including optional integrations and examples.

## Basic Concepts

### Cancelable Operations

A `Cancelable` provides a context for managing async operations that can be cancelled from various sources:

```python
from hother.cancelable import Cancelable

async with Cancelable() as cancel:
    # Your async operation here
    result = await some_async_operation()
```

### Cancelation Sources

Operations can be cancelled from multiple sources:

1. **Timeout**: Cancel after a specified duration
2. **Token**: Manual cancelation via a token
3. **Signal**: OS signal handling (SIGINT, etc.)
4. **Condition**\*: Custom condition checking

*: we provide `ResourceConditionSource` to cancel on system resource using `psutil` - particularly suitable for IoT applications.

## Quick Examples

### Timeout Cancelation

```python
from hother.cancelable import Cancelable
from datetime import timedelta

# Using seconds
async with Cancelable.with_timeout(30.0) as cancel:
    result = await long_running_operation()

# Using timedelta
async with Cancelable.with_timeout(timedelta(minutes=5)) as cancel:
    result = await very_long_operation()
```

### Manual Cancelation

```python
from hother.cancelable import Cancelable, CancelationToken

# Create a token
token = CancelationToken()

# In your async operation
async def my_operation():
    async with Cancelable.with_token(token) as cancel:
        # This will be cancelled when token.cancel() is called
        await some_work()

# Cancel from elsewhere
await token.cancel()
```

### Progress Reporting

```python
async with Cancelable() as cancel:
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
async with Cancelable.with_timeout(60) as cancel:
    # Process async stream with automatic cancelation
    async for item in cancel.stream(async_data_source()):
        await process_item(item)
```

## Best Practices

1. **Always use context managers**: Ensures proper cleanup
   ```python
   async with Cancelable() as cancel:
       # Your code here
   ```

2. **Report progress for long operations**: Helps with monitoring
   ```python
   await cancel.report_progress("Processing batch", {"size": len(batch)})
   ```

3. **Handle cancelation gracefully**: Save partial results
   ```python
   try:
       async with Cancelable.with_timeout(30) as cancel:
           result = await process_all()
   except Exception:
       # Save partial results from cancel.context.partial_result
       pass
   ```

## Next Steps

- See the [Core Concepts](basics.md) to learn more about the concepts
- Read the [API Reference](reference/index.md) for detailed documentation
- Check out [Common Patterns](patterns.md) for advanced usage
- Explore the [Examples](examples/index.md) for complete examples
