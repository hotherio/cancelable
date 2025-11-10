# Tenacity Integration

Integrate [Tenacity](https://tenacity.readthedocs.io/), the powerful retry library for Python, with Cancelable to add cancelation-aware retry logic to your applications.

## Why Use Cancelable with Tenacity?

Tenacity provides excellent retry logic (exponential backoff, wait strategies, retry predicates), but it **can't cancel retries from outside the retry loop**.

Consider these scenarios that Tenacity alone can't handle:

- **User logs out** → Cancel their background retry operations
- **Client disconnects** (FastAPI) → Stop retrying API call
- **SIGTERM received** → Gracefully stop all retry loops
- **Circuit breaker opens** → Stop retries based on external state
- **GUI "Cancel" button clicked** → Stop retry from different thread
- **Parent operation cancelled** → Cancel all child retry operations

**Use Tenacity for retry logic. Use Cancelable for cancelation logic.**

## Installation

Install Tenacity alongside Cancelable:

=== "uv"
    ```bash
    uv add tenacity
    uv add cancelable
    ```

=== "pip"
    ```bash
    pip install tenacity
    pip install cancelable
    ```

## Quick Start

### Multiple Cancelation Sources

Here's what makes the integration powerful - **combining sources Tenacity doesn't support**:

```python
import signal
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential
from hother.cancelable import Cancelable, CancelationToken

# Create cancelation token for manual control
token = CancelationToken()

async def fetch_data_with_retry(url: str):
    # Combine multiple cancelation sources
    cancel = Cancelable.with_timeout(60)  # Overall 60s timeout
    cancel = cancel.combine(
        Cancelable.with_token(token),          # Manual cancel (user action)
        Cancelable.with_signal(signal.SIGINT) # Graceful shutdown (Ctrl+C)
    )

    async with cancel:
        wrapped_fetch = cancel.wrap(fetch_data)

        # Tenacity handles retry logic
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(5),
            wait=wait_exponential(min=2, max=30)
        ):
            with attempt:
                # Checks ALL cancelation sources before each attempt
                result = await wrapped_fetch(url)
                return result

# Later: cancel from another task or thread
await token.cancel("User clicked cancel button")
# Or from sync context: token.cancel_sync("User logged out")
```

**This gives you**:

- ⏱️ Timeout protection (60s max)
- 🛑 Manual cancelation (user control)
- 📡 Signal handling (graceful shutdown)
- 🔄 Smart retries (Tenacity's exponential backoff)

## Use Cases

### 1. FastAPI: Client Disconnect

**Problem**: Client closes browser while retry loop is running. Continue retrying?

**Solution**: Bind retry loop to request lifecycle:

```python
from fastapi import FastAPI, Request, Depends
from hother.cancelable.integrations.fastapi import cancelable_dependency
from tenacity import AsyncRetrying, stop_after_attempt, wait_fixed

app = FastAPI()

@app.post("/process")
async def process_data(
    request: Request,
    cancel: Cancelable = Depends(cancelable_dependency)  # (1)!
):
    """Retries automatically stop when client disconnects."""
    async with cancel:  # (2)!
        wrapped_process = cancel.wrap(expensive_operation)

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(10),
            wait=wait_fixed(2)
        ):
            with attempt:
                await cancel.report_progress(
                    f"Attempt {attempt.retry_state.attempt_number}/10"
                )
                result = await wrapped_process(request.data)
                return {"result": result}
```

1. FastAPI dependency provides cancelable that watches client disconnect
2. Retries stop immediately when client closes connection

**Why this matters**: Saves compute resources on abandoned requests

### 2. Signal Handling: Graceful Shutdown

**Problem**: SIGTERM received, need to stop all retry loops gracefully

**Solution**: Bind retry loops to signal handler:

```python
import signal
from tenacity import AsyncRetrying, stop_after_attempt
from hother.cancelable import Cancelable

async def background_worker():
    """Worker that stops gracefully on SIGTERM."""
    cancel = Cancelable.with_signal(signal.SIGTERM, signal.SIGINT)

    async with cancel:
        wrapped_task = cancel.wrap(process_task)

        while True:  # (1)!
            async for attempt in AsyncRetrying(stop=stop_after_attempt(3)):
                with attempt:
                    await wrapped_task()

            await anyio.sleep(1)

# Kubernetes sends SIGTERM → all retry loops stop → pod terminates gracefully
```

1. Outer loop continues until signal received, inner loop retries failed tasks

**Why this matters**: Clean shutdown in containerized environments

### 3. User-Initiated Cancelation

**Problem**: User starts long-running retry operation, then wants to cancel it

**Solution**: Provide cancel button/API using token:

```python
from tenacity import AsyncRetrying, stop_after_attempt
from hother.cancelable import Cancelable, CancelationToken

# Store tokens by user
user_operations: dict[str, CancelationToken] = {}

async def start_user_operation(user_id: str, data: list):
    """User starts a retrying background operation."""
    token = CancelationToken()
    user_operations[user_id] = token  # Store for later cancel

    async with Cancelable.with_token(token, name=f"user_{user_id}") as cancel:
        wrapped_op = cancel.wrap(expensive_operation)

        for item in data:
            async for attempt in AsyncRetrying(stop=stop_after_attempt(5)):
                with attempt:
                    await wrapped_op(item)

async def cancel_user_operation(user_id: str):
    """User clicks 'Cancel' button."""
    if token := user_operations.get(user_id):
        await token.cancel(f"Cancelled by user {user_id}")
        del user_operations[user_id]
```

**Why this matters**: User control over long-running operations

### 4. Circuit Breaker: Condition-Based Cancelation

**Problem**: External service degraded, stop wasting retries

**Solution**: Use condition source to monitor circuit breaker:

```python
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential
from hother.cancelable import Cancelable

class CircuitBreaker:
    def __init__(self):
        self.is_open = False
        self.failure_count = 0

    def record_failure(self):
        self.failure_count += 1
        if self.failure_count >= 5:
            self.is_open = True

    def record_success(self):
        self.failure_count = 0
        self.is_open = False

breaker = CircuitBreaker()

async def api_call_with_circuit_breaker():
    """Stops retrying when circuit opens."""
    cancel = Cancelable.with_timeout(60)
    cancel = cancel.combine(
        Cancelable.with_condition(
            lambda: breaker.is_open,  # (1)!
            check_interval=0.5,
            condition_name="circuit_open"
        )
    )

    async with cancel:
        wrapped_call = cancel.wrap(external_api_call)

        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(10),
            wait=wait_exponential(min=1, max=30)
        ):
            with attempt:
                try:
                    result = await wrapped_call()
                    breaker.record_success()
                    return result
                except Exception:
                    breaker.record_failure()
                    raise
```

1. Check condition every 500ms - cancel all retries if circuit opens

**Why this matters**: Prevents retry storms when service is down

### 5. Thread-Safe Cancelation

**Problem**: Need to cancel async retry loop from GUI thread or signal handler

**Solution**: Use `cancel_sync()` for thread-safe cancelation:

```python
import threading
from tenacity import AsyncRetrying, stop_after_attempt
from hother.cancelable import Cancelable, CancelationToken

token = CancelationToken()

# Async retry loop
async def retry_operation():
    async with Cancelable.with_token(token) as cancel:
        wrapped_op = cancel.wrap(long_operation)

        async for attempt in AsyncRetrying(stop=stop_after_attempt(10)):
            with attempt:
                result = await wrapped_op()
                return result

# GUI button handler (different thread)
def on_cancel_button_clicked():
    """Called from GUI thread."""
    token.cancel_sync("User clicked cancel")  # (1)!

# Or signal handler (different context)
def signal_handler(signum, frame):
    """Called from signal handler."""
    token.cancel_sync(f"Received signal {signum}")

signal.signal(signal.SIGINT, signal_handler)
```

1. Thread-safe cancelation from any context

**Why this matters**: Enables cross-thread coordination

## Integration Patterns

### The Core Pattern

```python
# 1. Create cancelable with sources
cancel = Cancelable.with_timeout(60)
cancel = cancel.combine(
    Cancelable.with_token(token),
    Cancelable.with_signal(signal.SIGTERM)
)

# 2. Wrap operation once
async with cancel:
    wrapped = cancel.wrap(operation)

    # 3. Tenacity handles retry logic
    async for attempt in AsyncRetrying(...):
        with attempt:
            result = await wrapped()  # Checks cancelation sources
```

### Pre-wrap Operations (Recommended)

Wrap once before the retry loop for efficiency:

```python
async with Cancelable.with_timeout(60) as cancel:
    wrapped_op = cancel.wrap(operation)  # (1)!

    async for attempt in AsyncRetrying(stop=stop_after_attempt(3)):
        with attempt:
            result = await wrapped_op()  # (2)!
```

1. Wrap once for efficiency
2. Call many times - cancelation checked before each attempt

### Scoped Wrapping (Alternative)

Use `wrapping()` context manager for scoped wrapping:

```python
async with Cancelable.with_timeout(30) as cancel:
    async for attempt in AsyncRetrying(stop=stop_after_attempt(3)):
        with attempt:
            async with cancel.wrapping() as wrap:
                result = await wrap(operation)
```

## Tenacity Features

### Wait Strategies with Jitter

Prevent thundering herd with jitter:

```python
from tenacity import wait_exponential, wait_random

async with Cancelable.with_token(token) as cancel:
    wrapped = cancel.wrap(api_call)

    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(8),
        wait=wait_exponential(min=2, max=30) + wait_random(0, 2)  # (1)!
    ):
        with attempt:
            result = await wrapped()
```

1. Exponential backoff + random 0-2s jitter

### Retry Predicates

Only retry specific errors:

```python
import httpx
from tenacity import retry_if_exception_type

async with Cancelable.with_timeout(60) as cancel:
    wrapped = cancel.wrap(fetch)

    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type((  # (1)!
            httpx.ConnectError,
            httpx.TimeoutException
        ))
    ):
        with attempt:
            result = await wrapped()
```

1. Only retry network errors, not client errors (4xx)

## Complete Examples

### Example: Multi-User Background Jobs

```python
import signal
from tenacity import AsyncRetrying, stop_after_attempt, wait_fixed
from hother.cancelable import Cancelable, CancelationToken, OperationRegistry

user_tokens: dict[str, CancelationToken] = {}

async def process_user_data(user_id: str, items: list):
    """Process data with retry, cancelable by user or signal."""
    token = CancelationToken()
    user_tokens[user_id] = token

    cancel = Cancelable.with_timeout(300, name=f"user_{user_id}_job")
    cancel = cancel.combine(
        Cancelable.with_token(token),
        Cancelable.with_signal(signal.SIGTERM)
    )

    async with cancel:
        wrapped_process = cancel.wrap(process_item)

        for item in items:
            async for attempt in AsyncRetrying(
                stop=stop_after_attempt(3),
                wait=wait_fixed(2)
            ):
                with attempt:
                    await cancel.report_progress(
                        f"Processing {item}",
                        {"user": user_id, "item": item}
                    )
                    await wrapped_process(user_id, item)

# Cancel specific user
async def cancel_user_job(user_id: str):
    if token := user_tokens.get(user_id):
        await token.cancel(f"User {user_id} requested cancel")

# Cancel all users
async def cancel_all_jobs():
    registry = OperationRegistry.get_instance()
    await registry.cancel_all(
        name_pattern="user_*",
        reason=CancelationReason.MANUAL
    )
```

### Example: Streaming with Retry

```python
from tenacity import AsyncRetrying, stop_after_attempt, wait_fixed
from hother.cancelable import Cancelable

async def process_stream_with_retry(stream_source, request: Request):
    """Process stream with retry, stops on client disconnect."""
    cancel = Cancelable.with_timeout(300)
    # Assuming FastAPI passes request that can be checked for disconnect

    async with cancel:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_fixed(5)
        ):
            with attempt:
                # Each retry gets fresh stream
                stream = cancel.wrap(stream_source)

                async for item in await stream():
                    yield item
```

## Best Practices

### 1. Combine Multiple Sources

Don't just use timeout - that's what Tenacity already does:

```python
# ❌ Weak - just timeout (Tenacity can do this)
async with Cancelable.with_timeout(60) as cancel:
    async for attempt in AsyncRetrying(...):
        ...

# ✅ Strong - multiple sources (Tenacity can't do this)
cancel = Cancelable.with_timeout(60)
cancel = cancel.combine(
    Cancelable.with_token(user_token),
    Cancelable.with_signal(signal.SIGTERM)
)
```

### 2. Report Progress

Track retry attempts for observability:

```python
async with Cancelable(name="fetch") as cancel:
    cancel.on_progress(lambda op_id, msg, meta: logger.info(msg))

    wrapped = cancel.wrap(operation)
    async for attempt in AsyncRetrying(stop=stop_after_attempt(5)):
        with attempt:
            await cancel.report_progress(
                f"Attempt {attempt.retry_state.attempt_number}/5",
                {"attempt": attempt.retry_state.attempt_number}
            )
            result = await wrapped()
```

### 3. Handle Exception Types Correctly

Distinguish between cancelation and retry exhaustion:

```python
from tenacity import RetryError
import anyio

try:
    async with cancel:
        async for attempt in AsyncRetrying(...):
            with attempt:
                result = await wrapped()
except anyio.get_cancelled_exc_class():
    logger.warning("Operation cancelled")  # (1)!
except RetryError as e:
    logger.error(f"All retries exhausted: {e}")  # (2)!
```

1. Canceled by timeout, token, signal, or condition
2. Tenacity gave up after all retry attempts

### 4. Use Thread-Safe Methods

When canceling from different threads:

```python
# ✅ Correct - thread-safe
token.cancel_sync("From GUI thread")

# ❌ Wrong - not thread-safe
await token.cancel("From GUI thread")  # Can't await in sync context!
```

### 5. Add Jitter

Prevent thundering herd in distributed systems:

```python
from tenacity import wait_exponential, wait_random

async for attempt in AsyncRetrying(
    wait=wait_exponential(min=1, max=30) + wait_random(0, 2)
):
    ...
```

## Troubleshooting

### Issue: Retries Not Stopping on Cancelation

**Problem**: Wrapped operation ignores cancelation.

**Solution**: Ensure you're inside the cancelable context:

```python
# ❌ Wrong - not in context
cancel = Cancelable.with_timeout(30)
wrapped = cancel.wrap(operation)
async for attempt in AsyncRetrying(...):
    await wrapped()  # Won't check cancelation!

# ✅ Correct - inside context
async with cancel:
    wrapped = cancel.wrap(operation)
    async for attempt in AsyncRetrying(...):
        await wrapped()  # Checks cancelation!
```

### Issue: "Why not just use Tenacity's stop_after_delay?"

**Answer**: If you only need timeout, use Tenacity alone! But if you need:
- Manual cancelation (user action)
- Signal handling (graceful shutdown)
- Client disconnect detection
- Cross-thread cancelation
- Condition-based cancelation

Then you need Cancelable + Tenacity.

### Issue: Too Many Nested Context Managers

**Solution**: Use `wrap()` instead of `wrapping()`:

```python
# ❌ Complex
async with cancel:
    async for attempt in AsyncRetrying(...):
        with attempt:
            async with cancel.wrapping() as wrap:
                result = await wrap(operation)

# ✅ Simple
async with cancel:
    wrapped = cancel.wrap(operation)
    async for attempt in AsyncRetrying(...):
        with attempt:
            result = await wrapped()
```

## API Reference

### `wrap()` Method

```python
def wrap(self, operation: Callable[..., Awaitable[R]]) -> Callable[..., Awaitable[R]]
```

Wrap an async operation to check cancelation before each call.

**Example:**
```python
async with Cancelable.with_timeout(30) as cancel:
    wrapped = cancel.wrap(operation)
    result = await wrapped()  # Checks cancelation first
```

### `wrapping()` Context Manager

```python
@asynccontextmanager
async def wrapping(self) -> AsyncIterator[Callable]
```

Async context manager for scoped wrapping.

**Example:**
```python
async with Cancelable.with_timeout(30) as cancel:
    async with cancel.wrapping() as wrap:
        result = await wrap(operation)
```

## See Also

- [Tenacity Documentation](https://tenacity.readthedocs.io/) - Full Tenacity library docs
- [Core Concepts](../basics.md) - Understanding Cancelable
- [FastAPI Integration](fastapi.md) - Request lifecycle binding
- [Advanced Patterns](../patterns.md) - Production patterns
