# Basic Examples

This section covers the fundamental concepts of the cancelable library through practical examples.

## Basic Cancellation Context Manager

The core of cancelable is the `Cancellable` context manager, which provides a scope for operations that can be cancelled.

```python
from hother.cancelable import Cancellable

async def basic_operation():
    async with Cancellable(name="my_operation") as cancel:
        # Your cancellable operation here
        await do_work()
```

**Key Features:**
- Automatic cleanup on exit
- Progress reporting capabilities
- Operation naming for monitoring
- Exception propagation for cancellation

## Timeout Cancellation

Cancel operations automatically after a time limit.

```python
from hother.cancelable import Cancellable

# Cancel after 30 seconds
async with Cancellable.with_timeout(30.0) as cancel:
    await long_running_operation()

# Cancel after 5 minutes
async with Cancellable.with_timeout(timedelta(minutes=5)) as cancel:
    await very_long_operation()
```

**Use Cases:**
- API requests with timeouts
- Batch processing with time limits
- User-initiated operations that shouldn't run indefinitely

## Manual Cancellation with Tokens

Use `CancellationToken` for explicit cancellation control.

```python
from hother.cancelable import Cancellable, CancellationToken

async def cancellable_operation(token: CancellationToken):
    async with Cancellable.with_token(token) as cancel:
        while not token.is_cancelled:
            await process_next_item()

# Cancel from another task
await token.cancel(message="User requested cancellation")
```

**Benefits:**
- Decoupled cancellation logic
- Reusable across multiple operations
- Thread-safe cancellation signaling

## Decorated Functions

Apply cancellation to functions using decorators.

```python
from hother.cancelable import cancellable

@cancellable(timeout=60.0, name="data_processor")
async def process_data(data, cancellable=None):
    """Process data with automatic timeout cancellation."""
    for item in data:
        await cancellable.report_progress(f"Processing {item}")
        await process_item(item)
    return processed_data

# Call the decorated function
result = await process_data(large_dataset)
```

**Advantages:**
- Declarative cancellation configuration
- Automatic progress reporting
- Consistent error handling

## Running the Examples

```bash
# Basic cancellation concepts
python examples/01_basics/01_basic_cancellation.py

# Timeout examples
python examples/01_basics/02_timeout_cancellation.py

# Manual token cancellation
python examples/01_basics/03_manual_cancellation.py

# Decorator patterns
python examples/01_basics/04_decorated_functions.py
```

## Next Steps

- [Advanced Patterns](../advanced.md) - Combining cancellation sources
- [Integration Examples](../integrations.md) - Framework integrations
- [API Reference](../../reference/index.md) - Complete API documentation</content>
</xai:function_call