# Backend Validation Examples

This directory contains examples demonstrating cancellation capabilities with both anyio and pure asyncio.

## Purpose

These examples validate that both backends can handle:
1. **Cancellation from another thread** - Critical for integrating with sync code
2. **Cancellation from another async task** - Critical for coordinating async operations

## Examples

### Anyio (Current Implementation)

1. **`anyio_cancel_from_thread.py`**
   - Uses `hother.cancelable` with `CancellationToken`
   - Demonstrates thread-safe cancellation using `anyio.from_thread.run_sync()`
   - Shows that current library handles thread-based cancellation

2. **`anyio_cancel_from_async.py`**
   - Uses `hother.cancelable` with `CancellationToken`
   - Demonstrates task-to-task cancellation
   - Shows parent-child cancellation relationships

### Pure Asyncio (Proof of Concept)

3. **`asyncio_cancel_from_thread.py`**
   - Standalone example using only `asyncio` (no anyio)
   - Uses `loop.call_soon_threadsafe()` for thread safety
   - Demonstrates equivalent functionality to anyio version

4. **`asyncio_cancel_from_async.py`**
   - Standalone example using only `asyncio` (no anyio)
   - Shows task-to-task cancellation
   - Demonstrates timeout and direct task cancellation

## Running the Examples

### Anyio Examples (require library)
```bash
# Cancel from thread
uv run python examples/backend_validation/anyio_cancel_from_thread.py

# Cancel from async task
uv run python examples/backend_validation/anyio_cancel_from_async.py
```

### Pure Asyncio Examples (standalone)
```bash
# Cancel from thread (no dependencies)
python examples/backend_validation/asyncio_cancel_from_thread.py

# Cancel from async task (no dependencies)
python examples/backend_validation/asyncio_cancel_from_async.py
```

## Key Findings

### Thread-Based Cancellation

**Anyio Current Implementation:**
- ❌ **DOES NOT SUPPORT** true thread-based cancellation from regular Python threads
- `CancellationToken.cancel()` is async-only, requires async context
- `anyio.from_thread.run_sync()` only works in anyio worker threads (not regular Python threads)
- Would require adding a synchronous, thread-safe `cancel_sync()` method
- Current workaround: Use anyio worker threads (`anyio.to_thread.run_sync()`)

**Asyncio Approach:**
- ✅ **FULLY SUPPORTS** thread-based cancellation
- Use `loop.call_soon_threadsafe()` to schedule event setting from threads
- Store reference to event loop for thread-safe signaling
- Token checks cancellation flag synchronously
- Clean separation between thread-safe signaling and async waiting

**Conclusion:** ❌ Current anyio implementation CANNOT handle thread-based cancellation from regular Python threads. Asyncio CAN handle it with proper design.

### Async Task Cancellation

**Anyio Approach:**
- ✅ WORKS with `anyio.create_task_group()` for structured concurrency
- Direct token cancellation from any async task
- Automatic cleanup and error propagation
- Token callbacks trigger scope cancellation

**Asyncio Approach:**
- ✅ WORKS with `asyncio.create_task()` and `asyncio.gather()`
- Direct task cancellation via `task.cancel()`
- Token-based coordination for shared cancellation state
- Manual cancellation checking in worker tasks

**Conclusion:** ✅ Both backends can handle task-to-task cancellation

### Timeout Cancellation

**Anyio:**
- `anyio.CancelScope(deadline=...)`
- Integrated with monitoring infrastructure

**Asyncio:**
- Python 3.11+: `async with asyncio.timeout(seconds)`
- Python 3.10-: `await asyncio.wait_for(coro, timeout=seconds)`
- Both raise `asyncio.CancelledError` / `asyncio.TimeoutError`

**Conclusion:** ✅ Both backends support timeout-based cancellation

## Implementation Notes for Backend Abstraction

Based on these examples, the backend abstraction layer needs:

1. **Thread Safety Primitives** - CRITICAL DIFFERENCE
   - Anyio: Current implementation does NOT support thread cancellation
     - Would need: Synchronous `cancel_sync()` method with thread-safe state updates
     - Would need: `loop.call_soon_threadsafe()` equivalent for anyio
   - Asyncio: `loop.call_soon_threadsafe()` + stored loop reference (WORKS)

2. **Cancellation Signaling**
   - Anyio: `anyio.Event()` (async-only)
   - Asyncio: `asyncio.Event()` (async-only)
   - Both have compatible APIs for async contexts
   - **NEW REQUIREMENT**: Synchronous cancellation flag for thread-safe checking

3. **Task Monitoring**
   - Both support background tasks
   - Both can cancel tasks via exception propagation

4. **Timeout Management**
   - Anyio: `CancelScope` with deadline
   - Asyncio: Version-specific (`timeout()` or `wait_for()`)

## Critical Findings Summary

**THREAD CANCELLATION LIMITATION DISCOVERED:**

The current anyio-based implementation **does not support thread-based cancellation** from regular Python threads because:

1. `CancellationToken.cancel()` is async-only
2. No synchronous cancel method exists
3. Cannot call async methods from regular threads without anyio worker thread context

**Required Changes for Backend Abstraction:**

To support both anyio and asyncio with full thread-cancellation capability:

1. Add synchronous `cancel_sync()` method to `CancellationToken`
2. Use thread-safe primitives for state updates (threading.Lock, not anyio.Lock)
3. Use `loop.call_soon_threadsafe()` pattern for both backends
4. Keep async `cancel()` for async contexts
5. Separate thread-safe state management from async event notification

## GenAI Streaming Validation

**NEW:** Real-world validation with Google GenAI LLM streaming + keyboard cancellation

See [GENAI_STREAMING_RESULTS.md](./GENAI_STREAMING_RESULTS.md) for detailed results.

**Summary:**
- ✅ **Asyncio + GenAI**: Full working implementation with pynput keyboard integration
- ⚠️ **Anyio + GenAI**: Streaming works, keyboard integration needs refinement
- ✅ LLM streaming works identically on both backends
- ❌ Anyio has no `call_soon_threadsafe` equivalent, requires polling workarounds

**Scripts:**
- `asyncio_genai_streaming.py` - Working validation with pause/resume
- `anyio_genai_streaming.py` - Streaming works, keyboard needs fix

**Key Finding:** Real-world LLM streaming confirms asyncio's superior thread-safety support for external integrations like keyboard listeners and signal handlers.

## Next Steps

1. ✅ Validated cancellation patterns - **FOUND CRITICAL LIMITATION**
2. ✅ Validated real-world LLM streaming use case - **CONFIRMS ASYNCIO ADVANTAGES**
3. 🔄 Design backend abstraction layer that supports thread cancellation
4. 🔄 Add synchronous cancel method to CancellationToken
5. 🔄 Implement asyncio backend using patterns from these examples
6. 🔄 Ensure feature parity between backends (with documented limitations)
