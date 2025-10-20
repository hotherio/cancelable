# Troubleshooting Guide

This guide helps you resolve common issues and understand limitations when using the cancelable library.

## Thread Cancellation Limitations

### Issue: Cannot cancel from regular Python threads

**Symptoms:**
- `CancellationToken.cancel()` fails when called from regular Python threads
- Operations don't cancel when triggered from signal handlers or GUI threads
- Error: "RuntimeError: cannot call async function from non-async context"

**Root Cause:**
The current anyio-based implementation only supports async cancellation. Regular Python threads cannot call async methods without an anyio worker thread context.

**Workarounds:**
1. Use anyio worker threads:
```python
import anyio

# Instead of calling from regular thread
await anyio.to_thread.run_sync(cancel_operation)

# Use anyio's thread pool for cancellable operations
async with anyio.create_task_group() as tg:
    tg.start_soon(anyio.to_thread.run_sync, cancellable_work)
```

2. Use signal handlers with asyncio backend (see backend validation examples)

**Future Fix:**
The library will add synchronous cancellation methods for full thread support.

## Backend Differences

### AnyIO vs AsyncIO Behavior

**AnyIO (Current Default):**
- ✅ Full async task cancellation
- ✅ Structured concurrency with task groups
- ✅ Timeout cancellation
- ❌ Limited thread cancellation support

**AsyncIO (Alternative):**
- ✅ Full thread cancellation support
- ✅ Signal handler integration
- ✅ Keyboard interrupt handling
- ⚠️ Less structured concurrency patterns

**Recommendation:**
- Use AnyIO for pure async applications
- Use AsyncIO for applications needing thread cancellation
- See `examples/backend_validation/` for implementation differences

## Common Runtime Errors

### "CancelScope not properly closed"

**Cause:** Improper async context manager usage
**Fix:**
```python
# Correct usage
async with Cancellable() as cancel:
    await operation()

# Avoid this
cancel = Cancellable()
try:
    await operation()
finally:
    await cancel.__aexit__(None, None, None)
```

### Import Errors

**Error:** `ModuleNotFoundError: No module named 'greenlet'`
**Fix:** Install SQLAlchemy dependencies
```bash
uv add greenlet  # For SQLAlchemy async support
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

### Slow Cancellation Propagation

**Cause:** Too many concurrent operations
**Fix:** Use operation limits and batching
```python
# Limit concurrent operations
async with Cancellable(name="batch_processor") as cancel:
    semaphore = asyncio.Semaphore(10)  # Max 10 concurrent
    # ... process items with semaphore
```

## Integration Issues

### FastAPI Request Cancellation

**Issue:** Requests not cancelling properly
**Fix:** Use the FastAPI integration dependency
```python
from hother.cancelable.integrations.fastapi import cancellable_dependency

@app.post("/process")
async def process_data(cancel: Cancellable = Depends(cancellable_dependency)):
    async with cancel:
        return await process_large_dataset()
```

### HTTPX Timeout Conflicts

**Issue:** Double timeout handling
**Fix:** Disable HTTPX timeouts when using cancelable
```python
import httpx
from hother.cancelable.integrations.httpx import CancellableClient

# Let cancelable handle timeouts
async with CancellableClient(timeout=None) as client:
    async with Cancellable.with_timeout(30.0):
        response = await client.get(url)
```

### SQLAlchemy Connection Pooling

**Issue:** Connections not released on cancellation
**Fix:** Use cancellable session wrapper
```python
from hother.cancelable.integrations.sqlalchemy import CancellableAsyncSession

async with CancellableAsyncSession() as session:
    async with Cancellable.with_timeout(10.0):
        result = await session.execute(query)
        # Connections properly released even on cancellation
```

## Debugging Techniques

### Enable Debug Logging

```python
from hother.cancelable.utils.logging import configure_logging

configure_logging(log_level="DEBUG")
# Now see detailed cancellation flow logs
```

### Monitor Active Operations

```python
from hother.cancelable import OperationRegistry

registry = OperationRegistry.get_instance()
operations = await registry.list_operations()
for op in operations:
    print(f"{op.name}: {op.status.value}")
```

### Check Cancellation State

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
- Consider using `CancellationToken` with manual triggers

### macOS File Monitoring

- Some file watching APIs may not work
- Use polling alternatives for file changes

### Linux Container Issues

- Signal handling may be limited in containers
- Ensure proper signal forwarding from host

## Getting Help

1. Check the examples in `examples/` directory
2. Review backend validation results in `examples/backend_validation/`
3. Enable debug logging for detailed traces
4. Check GitHub issues for similar problems

## Known Limitations

1. **Thread Cancellation:** Limited support in anyio backend
2. **Windows Signals:** Reduced signal handler support
3. **Memory Usage:** Operation registry grows without cleanup
4. **Large Batches:** Performance degradation with 1000+ concurrent operations

These limitations will be addressed in future releases. See the backend validation examples for current workarounds.</content>
</xai:function_call</xai:function_call