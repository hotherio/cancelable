# Basic Usage Examples

This guide covers the fundamental usage patterns of the cancelable library.

## Getting Started

### Installation

```bash
uv add hother-cancelable
```

### Basic Imports

```python
from hother.cancelable import (
    Cancellable,
    CancellationToken,
    cancellable,
    with_timeout,
    OperationStatus,
    CancellationReason,
)
```

## Timeout-Based Cancellation

### Simple Timeout

```python
import asyncio
from hother.cancelable import Cancellable

async def long_operation():
    """Simulate a long-running operation."""
    await asyncio.sleep(5)
    return "Operation completed"

async def main():
    try:
        # This will timeout after 2 seconds
        async with Cancellable.with_timeout(2.0) as cancel:
            result = await long_operation()
            print(result)  # This won't be reached
    except asyncio.CancelledError:
        print("Operation timed out!")

asyncio.run(main())
```

### Timeout with Progress Reporting

```python
async def operation_with_progress():
    async with Cancellable.with_timeout(10.0) as cancel:
        # Add progress callback
        cancel.on_progress(
            lambda op_id, msg, meta: print(f"Progress: {msg}")
        )
        
        for i in range(5):
            await cancel.report_progress(
                f"Step {i+1}/5 completed",
                {"step": i+1, "total": 5}
            )
            await asyncio.sleep(1)
        
        return "All steps completed"
```

## Manual Cancellation

### Using CancellationToken

```python
async def cancellable_download(url: str, token: CancellationToken):
    """Download that can be cancelled manually."""
    async with Cancellable.with_token(token) as cancel:
        cancel.on_start(lambda ctx: print(f"Starting download: {url}"))
        cancel.on_cancel(lambda ctx: print(f"Download cancelled: {ctx.cancel_reason}"))
        
        # Simulate download
        for i in range(10):
            await asyncio.sleep(0.5)
            print(f"Downloaded {(i+1)*10}%")
        
        return f"Downloaded {url}"

async def main():
    # Create a cancellation token
    token = CancellationToken()
    
    # Start download in background
    download_task = asyncio.create_task(
        cancellable_download("https://example.com/file.zip", token)
    )
    
    # Cancel after 2 seconds
    await asyncio.sleep(2)
    await token.cancel("User requested cancellation")
    
    # Wait for task to handle cancellation
    try:
        result = await download_task
    except asyncio.CancelledError:
        print("Download was cancelled")

asyncio.run(main())
```

### Parent-Child Cancellation

```python
async def parent_operation():
    async with Cancellable.with_timeout(10.0) as parent:
        print("Parent operation started")
        
        # Create child operation
        async with Cancellable(parent=parent) as child:
            print("Child operation started")
            
            # If parent is cancelled, child is also cancelled
            await asyncio.sleep(5)
            
            print("Child operation completed")
        
        print("Parent operation completed")
```

## Function Decorators

### Basic Decorator Usage

```python
from hother.cancelable import cancellable

@cancellable(timeout=5.0)
async def process_data(items: list, cancellable: Cancellable = None):
    """Process items with automatic timeout."""
    results = []
    
    for i, item in enumerate(items):
        # Report progress
        await cancellable.report_progress(
            f"Processing item {i+1}/{len(items)}",
            {"current": i+1, "total": len(items)}
        )
        
        # Process item
        result = await process_item(item)
        results.append(result)
    
    return results

# Usage
async def main():
    items = [1, 2, 3, 4, 5]
    try:
        results = await process_data(items)
        print(f"Processed {len(results)} items")
    except asyncio.CancelledError:
        print("Processing timed out")
```

### Decorator with Custom Configuration

```python
@cancellable(
    timeout=30.0,
    register_globally=True,  # Register with global registry
    name="data_processor"
)
async def complex_processing(data: dict, cancellable: Cancellable = None):
    # Set up callbacks
    cancellable.on_cancel(
        lambda ctx: logger.warning(f"Processing cancelled: {ctx.cancel_reason}")
    )
    
    # Process data
    return await perform_analysis(data)
```

## Combining Cancellation Sources

### Multiple Cancellation Conditions

```python
import signal

async def multi_cancellable_operation():
    # Create individual cancellables
    timeout_cancel = Cancellable.with_timeout(30.0)
    signal_cancel = Cancellable.with_signal(signal.SIGINT)
    token = CancellationToken()
    manual_cancel = Cancellable.with_token(token)
    
    # Combine them - cancels if ANY condition is met
    combined = timeout_cancel.combine(signal_cancel, manual_cancel)
    
    async with combined as cancel:
        cancel.on_cancel(
            lambda ctx: print(f"Cancelled due to: {ctx.cancel_reason}")
        )
        
        # Long running operation
        await long_computation()
```

### Conditional Cancellation

```python
# Global flag that can be set by other parts of the application
should_stop = False

async def conditional_operation():
    async with Cancellable.with_condition(
        lambda: should_stop,  # Check condition
        check_interval=0.5,   # Check every 0.5 seconds
        condition_name="stop_flag"
    ) as cancel:
        # Operation continues until should_stop becomes True
        while True:
            await do_work()
            await asyncio.sleep(1)
```

## Stream Processing

### Basic Stream Cancellation

```python
async def process_stream():
    async with Cancellable.with_timeout(60.0) as cancel:
        # Wrap any async iterator
        async for item in cancel.stream(
            fetch_items(),  # Your async iterator
            report_interval=10  # Report every 10 items
        ):
            # Process each item
            result = await process_item(item)
            
            # Cancellation is checked automatically between items
```

### Stream with Buffering

```python
async def fetch_items():
    """Async generator that yields items."""
    for i in range(100):
        await asyncio.sleep(0.1)
        yield f"item_{i}"

async def buffered_stream_processing():
    async with Cancellable.with_timeout(10.0) as cancel:
        try:
            async for item in cancel.stream(
                fetch_items(),
                buffer_partial=True  # Keep partial results
            ):
                print(f"Processing {item}")
                
        except asyncio.CancelledError:
            # Access partial results
            partial = cancel.context.partial_result
            print(f"Processed {partial['count']} items before cancellation")
            print(f"Last items: {partial['buffer'][-5:]}")
```

## Error Handling

### Handling Different Cancellation Types

```python
from hother.cancelable import (
    TimeoutCancellation,
    ManualCancellation,
    SignalCancellation,
)

async def robust_operation():
    try:
        async with Cancellable.with_timeout(30.0) as cancel:
            result = await do_work()
            return result
            
    except TimeoutCancellation as e:
        logger.error(f"Operation timed out: {e.message}")
        # Handle timeout specifically
        return None
        
    except ManualCancellation as e:
        logger.info(f"Operation cancelled by user: {e.message}")
        # Handle manual cancellation
        return None
        
    except SignalCancellation as e:
        logger.warning(f"Operation cancelled by signal: {e.signal}")
        # Handle signal cancellation
        return None
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise
```

## Shielding Critical Operations

### Protecting Cleanup Code

```python
async def operation_with_cleanup():
    resource = None
    
    async with Cancellable.with_timeout(10.0) as cancel:
        try:
            # Acquire resource
            resource = await acquire_resource()
            
            # Do work (can be cancelled)
            result = await process_with_resource(resource)
            
            return result
            
        finally:
            # Shield cleanup from cancellation
            if resource:
                async with cancel.shield():
                    # This will complete even if cancelled
                    await release_resource(resource)
                    print("Resource cleaned up successfully")
```

## Global Operation Registry

### Monitoring Active Operations

```python
from hother.cancelable import OperationRegistry

async def monitored_operation():
    # Register globally
    async with Cancellable.with_timeout(
        60.0,
        name="data_import",
        register_globally=True
    ) as cancel:
        await import_data()

async def monitor_operations():
    registry = OperationRegistry.get_instance()
    
    # List all running operations
    operations = await registry.list_operations(
        status=OperationStatus.RUNNING
    )
    
    for op in operations:
        print(f"Running: {op.name} (ID: {op.id[:8]})")
        print(f"  Started: {op.start_time}")
        print(f"  Duration: {op.duration}s")
    
    # Get statistics
    stats = await registry.get_statistics()
    print(f"Total operations: {stats.total_operations}")
    print(f"Currently running: {stats.running}")
```

## Best Practices

1. **Always use async with**: Ensures proper cleanup
2. **Set reasonable timeouts**: Based on expected operation duration
3. **Report progress**: For long operations, keep users informed
4. **Handle cancellation gracefully**: Clean up resources properly
5. **Use appropriate cancellation source**: Timeout, manual, signal, or condition
6. **Combine sources when needed**: For flexible cancellation strategies
7. **Shield critical operations**: Protect cleanup code from cancellation

## Next Steps

- Explore [Stream Processing](stream_processing.md) for advanced streaming patterns
- Check out the Integration Guides for library-specific usage
- Review [Patterns](../patterns.md) for advanced usage patterns