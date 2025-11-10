# Troubleshooting Guide

This guide helps you resolve common issues and understand limitations when using the cancelable library.

## Common Runtime Errors

### "CancelScope not properly closed"

**Cause:** Improper async context manager usage
**Fix:**
```python
# Correct usage
async with Cancelable() as cancel:
    await operation()

# Avoid this
cancel = Cancelable()
try:
    await operation()
finally:
    await cancel.__aexit__(None, None, None)
```

### Signal Handler Issues

**Error:** Signals not working on Windows   
**Note:** Signal handling has limited support on Windows (primarily SIGINT)

## Performance Issues

### High Memory Usage

**Cause:** Operation registry not cleared   
**Fix:**
```python
from hother.cancelable import OperationRegistry

registry = OperationRegistry.get_instance()
await registry.clear_all()  # Clear completed operations
```

### Slow Cancelation Propagation

**Cause:** Too many concurrent operations   
**Fix:** Use operation limits and batching
```python
# Limit concurrent operations
async with Cancelable(name="batch_processor") as cancel:
    semaphore = asyncio.Semaphore(10)  # Max 10 concurrent
    # ... process items with semaphore
```

## Integration Issues

### FastAPI Request Cancelation

**Issue:** Requests not cancelling properly   
**Fix:** Use the FastAPI integration dependency
```python
from hother.cancelable.integrations.fastapi import cancelable_dependency

@app.post("/process")
async def process_data(cancel: Cancelable = Depends(cancelable_dependency)):
    async with cancel:
        return await process_large_dataset()
```

## Debugging Techniques

### Enable Debug Logging

Configure logging in your application to see detailed cancelation flow:

```python
import logging

# Configure logging in your application
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Enable debug logs for hother.cancelable
logging.getLogger("hother.cancelable").setLevel(logging.DEBUG)
```

### Monitor Active Operations

```python
from hother.cancelable import OperationRegistry

registry = OperationRegistry.get_instance()
operations = await registry.list_operations()
for op in operations:
    print(f"{op.name}: {op.status.value}")
```

### Check Cancelation State

```python
# Debug token state
print(f"Token cancelled: {token.is_cancelled}")
print(f"Reason: {token.reason}")
print(f"Message: {token.message}")

# Check operation context
print(f"Operation status: {cancel.context.status}")
print(f"Duration: {cancel.context.duration}")
```

## Platform-Specific Issues

### Windows Signal Handling

- SIGTERM not available
- Use SIGINT (Ctrl+C) only
- Consider using `CancelationToken` with manual triggers

### macOS File Monitoring

- Some file watching APIs may not work
- Use polling alternatives for file changes

### Linux Container Issues

- Signal handling may be limited in containers
- Ensure proper signal forwarding from host

## Getting Help

1. Check the examples in `examples/` directory
2. Enable debug logging for detailed traces
3. Check GitHub issues for similar problems
