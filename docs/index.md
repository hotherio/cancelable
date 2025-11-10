# Cancelable

**Comprehensive async cancelation for Python** - the missing piece for production-grade async operations.

[![PyPI version](https://badge.fury.io/py/hother-cancelable.svg)](https://pypi.org/project/hother-cancelable/)
[![Python versions](https://img.shields.io/pypi/pyversions/hother-cancelable)](https://pypi.org/project/hother-cancelable/)
[![License](https://img.shields.io/github/license/hotherio/cancelable)](https://github.com/hotherio/cancelable/blob/main/LICENSE)

## What is Cancelable?

Cancelable provides **streaming cancelation** and **thread-safe cancelation** for async Python. Cancel async streams at any point, bridge between threading and async contexts, and compose multiple cancelation sources (timeout + manual + signals + conditions) with built-in progress tracking and monitoring. It is built on top of **[anyio](https://github.com/agronholm/anyio)** and support `asyncio` backend.

```bash
pip install hother-cancelable
```

## Quick Example

```python
import threading
import time
import anyio
from hother.cancelable import Cancelable, CancelationToken, cancelable

# Create a cancellation token
token = CancelationToken()

# Cancel from another thread after 5 seconds
def monitor_thread():
    time.sleep(5.0)
    token.cancel_sync(message="Cancelled by monitor")  # (1)!

threading.Thread(target=monitor_thread, daemon=True).start()

# Progress tracking callback
def on_progress(op_id, message, metadata):
    progress = metadata.get('progress', 0)
    print(f"[Progress] {message} ({progress}%)")  # (2)!

# Using decorator with multiple conditions
@cancelable(timeout=10.0, name="data_processor")  # (3)!
async def process_data(cancel: Cancelable):
    # Register progress callback
    cancel.on_progress(on_progress)

    # Combine timeout with manual token
    cancel = cancel.combine(Cancelable.with_token(token))  # (4)!

    # Stream processing with cancellation
    async def data_stream():
        for i in range(100):
            await anyio.sleep(0.1)
            yield {"id": i, "data": f"item_{i}"}

    processed = []
    async for item in cancel.stream(data_stream(), report_interval=10):  # (5)!
        # Report progress periodically
        await cancel.report_progress(
            f"Processing item {item['id']}",
            {"progress": item['id'], "total": 100}  # (6)!
        )
        processed.append(item)

    return processed

# Run the operation
try:
    result = await process_data()
    print(f"Processed {len(result)} items")
except anyio.get_cancelled_exc_class():
    print(f"Cancelled: {token.message}")  # (7)!
```

1.  Thread-safe cancellation from regular Python threads
2.  Progress callback receives messages and metadata
3.  `@cancelable` decorator with timeout - auto-injects Cancelable parameter
4.  Combine decorator timeout with manual token - cancels on FIRST trigger
5.  Stream wrapper with automatic progress reporting every 10 items
6.  Manual progress reporting with custom metadata
7.  Handle cancellation and access the reason

## Framework Integration

Seamless integration with popular async frameworks:

### FastAPI

```python
from fastapi import FastAPI, Depends
from hother.cancelable.integrations.fastapi import cancelable_dependency

app = FastAPI()

@app.get("/process")
async def process_data(cancel: Cancelable = Depends(cancelable_dependency)):
    async with cancel:  # Auto-cancelled on client disconnect
        return await heavy_computation()
```

[Learn more about FastAPI integration →](integrations/fastapi.md){ .md-button }

### Tenacity (Retry)

```python
from tenacity import AsyncRetrying, stop_after_attempt

async with Cancelable.with_timeout(60.0, name="fetch") as cancel:
    wrapped_fetch = cancel.wrap(fetch_data)  # (1)!

    async for attempt in AsyncRetrying(stop=stop_after_attempt(3)):
        with attempt:
            result = await wrapped_fetch(url)  # (2)!
            return result
```

1. Wrap function to respect cancellation during retries
2. Retries up to 3 times, but stops immediately if cancelled

[Learn more about Tenacity integration →](integrations/tenacity.md){ .md-button }

## Common Use Cases

| Scenario | What Cancelable Provides |
|----------|--------------------------|
| **Web APIs** | Request timeouts + client disconnect + graceful shutdown |
| **Data Pipelines** | Progress tracking + timeout protection + manual stop |
| **Background Jobs** | Dashboard monitoring + multi-condition cancelation |
| **Stream Processing** | Condition-based stopping + buffer management |
| **Microservices** | Cross-service cancelation propagation |

## Next Steps

<div class="grid cards" markdown>

-   :material-clock-fast:{ .lg .middle } __Get Started__

    ---

    Install Cancelable and learn the basics in 5 minutes

    [:octicons-arrow-right-24: Installation](getting_started.md)

-   :material-book-open-variant:{ .lg .middle } __Core Concepts__

    ---

    Understand cancelation sources, operations, and monitoring

    [:octicons-arrow-right-24: Learn Concepts](basics.md)

-   :material-code-braces:{ .lg .middle } __Browse Examples__

    ---

    Complete runnable examples for common use cases

    [:octicons-arrow-right-24: View Examples](examples/index.md)

-   :material-api:{ .lg .middle } __API Reference__

    ---

    Complete API documentation for all modules

    [:octicons-arrow-right-24: API Docs](reference/index.md)

</div>

---

Built by the Hother team • [GitHub](https://github.com/hotherio/cancelable) • [PyPI](https://pypi.org/project/hother-cancelable/)
