# Backend Abstraction Plan: Asyncio + Anyio Support

## Executive Summary

This document outlines the plan to add dual backend support (asyncio + anyio) to the hother.cancelable library without changing the public API. The library currently has **critical bugs** where it mixes asyncio and anyio primitives, breaking anyio compatibility. This plan fixes those bugs and creates a clean abstraction layer.

## Current State Analysis

### Critical Issues Found

The library is currently **BROKEN** for pure anyio usage due to:

1. **timeout.py:70** - Uses `asyncio.create_task()` instead of anyio task groups
2. **condition.py:66** - Uses `asyncio.create_task()` instead of anyio task groups
3. **condition.py:81,132** - Uses `asyncio.CancelledError` instead of `anyio.get_cancelled_exc_class()`
4. **composite.py** - Likely has similar issues (needs investigation)

These bugs mean that any anyio application using TimeoutSource or ConditionSource will crash!

### Backend-Specific Operations Identified

Analysis of 19 files importing anyio revealed these backend-specific operations:

| Operation | Current (anyio) | Asyncio Equivalent | Usage Count |
|-----------|----------------|-------------------|-------------|
| Cancel Scope | `anyio.CancelScope()` | `asyncio.timeout()` / task cancel | ~30 uses |
| Exception Class | `anyio.get_cancelled_exc_class()` | `asyncio.CancelledError` | ~10 uses |
| Sleep/Checkpoint | `anyio.sleep()` | `asyncio.sleep()` | ~15 uses |
| Current Time | `anyio.current_time()` | `loop.time()` | ~3 uses |
| Lock | `anyio.Lock()` | `asyncio.Lock()` | ~5 uses |
| Task Creation | (none) | `asyncio.create_task()` | 3 BUGS! |
| Thread Pool | `anyio.to_thread.run_sync()` | `loop.run_in_executor()` | ~2 uses |
| Memory Streams | `anyio.create_memory_object_stream()` | `asyncio.Queue()` | 2 uses |
| Thread Safety | AnyioBridge (custom) | `loop.call_soon_threadsafe()` | 1 use |

### Files Requiring Changes

**Core Files (8):**
- `src/hother/cancelable/core/cancellable.py` - CancelScope usage
- `src/hother/cancelable/core/token.py` - Event, thread safety
- `src/hother/cancelable/core/registry.py` - Lock usage

**Source Files (5 - URGENT):**
- `src/hother/cancelable/sources/base.py` - CancelScope interface
- `src/hother/cancelable/sources/timeout.py` - **BROKEN** asyncio.create_task
- `src/hother/cancelable/sources/condition.py` - **BROKEN** asyncio.create_task
- `src/hother/cancelable/sources/composite.py` - Unknown status
- `src/hother/cancelable/sources/signal.py` - Thread safety

**Utility Files (3):**
- `src/hother/cancelable/utils/anyio_bridge.py` - Needs asyncio equivalent
- `src/hother/cancelable/utils/streams.py` - Stream operations
- `src/hother/cancelable/utils/testing.py` - Test helpers

**Integration Files (1):**
- `src/hother/cancelable/integrations/fastapi.py` - Framework integration

---

## Design Goals

1. **Zero API Changes** - Public API remains 100% unchanged
2. **Automatic Backend Detection** - No user configuration required (uses `sniffio`)
3. **Full Feature Parity** - All features work identically on both backends
4. **No Performance Regression** - Backend abstraction adds <1% overhead
5. **Backward Compatibility** - Existing code continues to work
6. **Fix Existing Bugs** - Remove all asyncio dependencies from anyio code paths

---

## Architecture Design

### 1. Backend Detection Strategy

Use `sniffio` to automatically detect the running async backend:

```python
# src/hother/cancelable/backends/detection.py
from __future__ import annotations

import sniffio
from typing import Literal

BackendType = Literal["asyncio", "anyio"]

def detect_backend() -> BackendType:
    """
    Detect which async backend is currently running.

    Returns:
        "asyncio" or "anyio" based on sniffio detection

    Raises:
        RuntimeError: If called outside async context
    """
    try:
        backend = sniffio.current_async_library()
        # sniffio returns "asyncio" or "trio" or "curio"
        # We map everything to either asyncio or anyio
        if backend == "asyncio":
            return "asyncio"
        else:
            # trio, curio, etc. all use anyio-compatible APIs
            return "anyio"
    except sniffio.AsyncLibraryNotFoundError:
        raise RuntimeError(
            "Backend detection failed - not in async context. "
            "Ensure you're calling from within an async function."
        )
```

### 2. Backend Abstraction Interface

Create abstract base class defining all backend operations:

```python
# src/hother/cancelable/backends/base.py
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any, TypeVar

T = TypeVar("T")

class AsyncBackend(ABC):
    """
    Abstract interface for async backend implementations.

    Provides a unified API for asyncio and anyio operations.
    """

    # ===== Cancel Scope Management =====

    @abstractmethod
    @asynccontextmanager
    async def create_cancel_scope(
        self,
        deadline: float | None = None,
        shield: bool = False,
    ) -> AsyncIterator[CancelScope]:
        """
        Create a cancellation scope.

        Args:
            deadline: Absolute deadline (from current_time())
            shield: Whether to shield from parent cancellation

        Yields:
            CancelScope object
        """
        ...

    # ===== Exception Handling =====

    @abstractmethod
    def get_cancelled_exc_class(self) -> type[BaseException]:
        """Get the backend-specific cancellation exception class."""
        ...

    # ===== Timing =====

    @abstractmethod
    async def sleep(self, seconds: float) -> None:
        """Sleep for specified duration (also acts as checkpoint)."""
        ...

    @abstractmethod
    def current_time(self) -> float:
        """Get current monotonic time."""
        ...

    # ===== Synchronization Primitives =====

    @abstractmethod
    def create_lock(self) -> Lock:
        """Create a backend-specific async lock."""
        ...

    @abstractmethod
    def create_event(self) -> Event:
        """Create a backend-specific async event."""
        ...

    # ===== Task Management =====

    @abstractmethod
    @asynccontextmanager
    async def create_task_group(self) -> AsyncIterator[TaskGroup]:
        """
        Create a task group for managing concurrent tasks.

        Yields:
            TaskGroup for starting tasks
        """
        ...

    # ===== Thread Safety =====

    @abstractmethod
    def call_soon_threadsafe(self, callback: Callable) -> None:
        """
        Schedule callback to run in event loop from any thread.

        Args:
            callback: Function to call (can be sync or async)
        """
        ...

    # ===== Thread Pool Execution =====

    @abstractmethod
    async def run_sync_in_thread(
        self,
        func: Callable[..., T],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """
        Run synchronous function in thread pool.

        Args:
            func: Synchronous function to run
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Result from function
        """
        ...

    # ===== Communication Primitives =====

    @abstractmethod
    def create_queue(self, max_size: int = 0) -> Queue[T]:
        """
        Create a backend-specific async queue.

        Args:
            max_size: Maximum queue size (0 = unlimited)

        Returns:
            Queue instance
        """
        ...


class CancelScope(ABC):
    """Abstract interface for cancel scopes."""

    @abstractmethod
    def cancel(self) -> None:
        """Cancel this scope."""
        ...

    @property
    @abstractmethod
    def cancel_called(self) -> bool:
        """Check if cancel() was called."""
        ...

    @property
    @abstractmethod
    def deadline(self) -> float | None:
        """Get the deadline (if any)."""
        ...

    @deadline.setter
    @abstractmethod
    def deadline(self, value: float | None) -> None:
        """Set the deadline."""
        ...


class Lock(ABC):
    """Abstract interface for locks."""

    @abstractmethod
    async def __aenter__(self) -> None: ...

    @abstractmethod
    async def __aexit__(self, *args) -> None: ...

    @abstractmethod
    async def acquire(self) -> None: ...

    @abstractmethod
    def release(self) -> None: ...


class Event(ABC):
    """Abstract interface for events."""

    @abstractmethod
    def set(self) -> None:
        """Set the event."""
        ...

    @abstractmethod
    def is_set(self) -> bool:
        """Check if event is set."""
        ...

    @abstractmethod
    async def wait(self) -> None:
        """Wait for event to be set."""
        ...


class TaskGroup(ABC):
    """Abstract interface for task groups."""

    @abstractmethod
    def start_soon(self, coro: Callable[..., Any], *args: Any) -> None:
        """
        Start a task in the background.

        Args:
            coro: Coroutine function to run
            *args: Arguments to pass
        """
        ...

    @property
    @abstractmethod
    def cancel_scope(self) -> CancelScope:
        """Get the task group's cancel scope."""
        ...


class Queue(ABC):
    """Abstract interface for queues."""

    @abstractmethod
    async def put(self, item: T) -> None: ...

    @abstractmethod
    async def get(self) -> T: ...

    @abstractmethod
    def put_nowait(self, item: T) -> None: ...

    @abstractmethod
    def get_nowait(self) -> T: ...
```

### 3. Anyio Backend Implementation

```python
# src/hother/cancelable/backends/anyio_backend.py
from __future__ import annotations

import anyio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any, TypeVar

from .base import (
    AsyncBackend,
    CancelScope as BaseCancelScope,
    Lock as BaseLock,
    Event as BaseEvent,
    TaskGroup as BaseTaskGroup,
    Queue as BaseQueue,
)
from ..utils.anyio_bridge import AnyioBridge

T = TypeVar("T")


class AnyioCancelScope(BaseCancelScope):
    """Anyio implementation of CancelScope."""

    def __init__(self, scope: anyio.CancelScope):
        self._scope = scope

    def cancel(self) -> None:
        self._scope.cancel()

    @property
    def cancel_called(self) -> bool:
        return self._scope.cancel_called

    @property
    def deadline(self) -> float | None:
        return self._scope.deadline

    @deadline.setter
    def deadline(self, value: float | None) -> None:
        self._scope.deadline = value

    def __enter__(self):
        return self._scope.__enter__()

    def __exit__(self, *args):
        return self._scope.__exit__(*args)


class AnyioLock(BaseLock):
    """Anyio implementation of Lock."""

    def __init__(self):
        self._lock = anyio.Lock()

    async def __aenter__(self):
        await self._lock.__aenter__()

    async def __aexit__(self, *args):
        await self._lock.__aexit__(*args)

    async def acquire(self):
        await self._lock.acquire()

    def release(self):
        self._lock.release()


class AnyioEvent(BaseEvent):
    """Anyio implementation of Event."""

    def __init__(self):
        self._event = anyio.Event()

    def set(self):
        self._event.set()

    def is_set(self) -> bool:
        return self._event.is_set()

    async def wait(self):
        await self._event.wait()


class AnyioTaskGroup(BaseTaskGroup):
    """Anyio implementation of TaskGroup."""

    def __init__(self, tg: anyio.abc.TaskGroup):
        self._tg = tg
        self._cancel_scope = AnyioCancelScope(tg.cancel_scope)

    def start_soon(self, coro: Callable[..., Any], *args: Any):
        self._tg.start_soon(coro, *args)

    @property
    def cancel_scope(self) -> AnyioCancelScope:
        return self._cancel_scope


class AnyioQueue(BaseQueue[T]):
    """Anyio implementation of Queue using memory object streams."""

    def __init__(self, max_size: int = 0):
        # anyio uses memory object streams instead of queues
        size = max_size if max_size > 0 else 1000  # Default buffer
        self._send, self._receive = anyio.create_memory_object_stream(size)

    async def put(self, item: T):
        await self._send.send(item)

    async def get(self) -> T:
        return await self._receive.receive()

    def put_nowait(self, item: T):
        self._send.send_nowait(item)

    def get_nowait(self) -> T:
        return self._receive.receive_nowait()


class AnyioBackend(AsyncBackend):
    """Anyio backend implementation."""

    @asynccontextmanager
    async def create_cancel_scope(
        self,
        deadline: float | None = None,
        shield: bool = False,
    ) -> AsyncIterator[AnyioCancelScope]:
        """Create an anyio cancel scope."""
        scope = anyio.CancelScope(deadline=deadline, shield=shield)
        wrapper = AnyioCancelScope(scope)
        with scope:
            yield wrapper

    def get_cancelled_exc_class(self) -> type[BaseException]:
        return anyio.get_cancelled_exc_class()

    async def sleep(self, seconds: float):
        await anyio.sleep(seconds)

    def current_time(self) -> float:
        return anyio.current_time()

    def create_lock(self) -> AnyioLock:
        return AnyioLock()

    def create_event(self) -> AnyioEvent:
        return AnyioEvent()

    @asynccontextmanager
    async def create_task_group(self) -> AsyncIterator[AnyioTaskGroup]:
        """Create an anyio task group."""
        async with anyio.create_task_group() as tg:
            yield AnyioTaskGroup(tg)

    def call_soon_threadsafe(self, callback: Callable):
        """Use AnyioBridge for thread-safe scheduling."""
        bridge = AnyioBridge.get_instance()
        bridge.call_soon_threadsafe(callback)

    async def run_sync_in_thread(
        self,
        func: Callable[..., T],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Run sync function in thread pool."""
        return await anyio.to_thread.run_sync(func, *args, **kwargs)

    def create_queue(self, max_size: int = 0) -> AnyioQueue[T]:
        return AnyioQueue(max_size)
```

### 4. Asyncio Backend Implementation

```python
# src/hother/cancelable/backends/asyncio_backend.py
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any, TypeVar

from .base import (
    AsyncBackend,
    CancelScope as BaseCancelScope,
    Lock as BaseLock,
    Event as BaseEvent,
    TaskGroup as BaseTaskGroup,
    Queue as BaseQueue,
)

T = TypeVar("T")


class AsyncioCancelScope(BaseCancelScope):
    """
    Asyncio implementation of CancelScope.

    Maps anyio's CancelScope to asyncio's timeout + task cancellation.
    """

    def __init__(self, deadline: float | None = None, shield: bool = False):
        self._deadline = deadline
        self._shield = shield
        self._cancel_called = False
        self._task: asyncio.Task | None = None
        self._timeout_handle: asyncio.TimerHandle | None = None

    def cancel(self):
        """Cancel the scope by cancelling the associated task."""
        self._cancel_called = True
        if self._task and not self._task.done():
            self._task.cancel()

    @property
    def cancel_called(self) -> bool:
        return self._cancel_called

    @property
    def deadline(self) -> float | None:
        return self._deadline

    @deadline.setter
    def deadline(self, value: float | None):
        self._deadline = value
        # Update timeout if we're already active
        if self._timeout_handle:
            self._timeout_handle.cancel()
            self._setup_timeout()

    def _setup_timeout(self):
        """Set up timeout handler if deadline is set."""
        if self._deadline is not None and not self._cancel_called:
            loop = asyncio.get_event_loop()
            current = loop.time()
            delay = max(0, self._deadline - current)
            self._timeout_handle = loop.call_later(delay, self.cancel)

    def __enter__(self):
        # Capture the current task
        try:
            self._task = asyncio.current_task()
        except RuntimeError:
            pass

        # Set up deadline monitoring
        self._setup_timeout()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Cancel timeout if it hasn't fired
        if self._timeout_handle:
            self._timeout_handle.cancel()

        # If we got CancelledError and we called cancel, suppress it
        # This matches anyio's behavior
        if exc_type is asyncio.CancelledError and self._cancel_called:
            # Scope handles the cancellation
            return True
        return False


class AsyncioLock(BaseLock):
    """Asyncio implementation of Lock."""

    def __init__(self):
        self._lock = asyncio.Lock()

    async def __aenter__(self):
        await self._lock.__aenter__()

    async def __aexit__(self, *args):
        await self._lock.__aexit__(*args)

    async def acquire(self):
        await self._lock.acquire()

    def release(self):
        self._lock.release()


class AsyncioEvent(BaseEvent):
    """Asyncio implementation of Event."""

    def __init__(self):
        self._event = asyncio.Event()

    def set(self):
        self._event.set()

    def is_set(self) -> bool:
        return self._event.is_set()

    async def wait(self):
        await self._event.wait()


class AsyncioTaskGroup(BaseTaskGroup):
    """
    Asyncio implementation of TaskGroup.

    Provides anyio-like task group API for asyncio.
    """

    def __init__(self):
        self._tasks: set[asyncio.Task] = set()
        self._cancel_scope = AsyncioCancelScope()
        self._entered = False

    def start_soon(self, coro: Callable[..., Any], *args: Any):
        """Start a task in the background."""
        if not self._entered:
            raise RuntimeError("TaskGroup not entered")

        task = asyncio.create_task(coro(*args))
        self._tasks.add(task)

        # Clean up when done
        task.add_done_callback(self._tasks.discard)

    @property
    def cancel_scope(self) -> AsyncioCancelScope:
        return self._cancel_scope

    async def __aenter__(self):
        self._entered = True
        self._cancel_scope.__enter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Wait for all tasks to complete
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self._cancel_scope.__exit__(exc_type, exc_val, exc_tb)
        self._entered = False


class AsyncioQueue(BaseQueue[T]):
    """Asyncio implementation of Queue."""

    def __init__(self, max_size: int = 0):
        self._queue = asyncio.Queue(maxsize=max_size)

    async def put(self, item: T):
        await self._queue.put(item)

    async def get(self) -> T:
        return await self._queue.get()

    def put_nowait(self, item: T):
        self._queue.put_nowait(item)

    def get_nowait(self) -> T:
        return self._queue.get_nowait()


class AsyncioBackend(AsyncBackend):
    """Asyncio backend implementation."""

    @asynccontextmanager
    async def create_cancel_scope(
        self,
        deadline: float | None = None,
        shield: bool = False,
    ) -> AsyncIterator[AsyncioCancelScope]:
        """Create an asyncio cancel scope."""
        scope = AsyncioCancelScope(deadline=deadline, shield=shield)
        with scope:
            yield scope

    def get_cancelled_exc_class(self) -> type[BaseException]:
        return asyncio.CancelledError

    async def sleep(self, seconds: float):
        await asyncio.sleep(seconds)

    def current_time(self) -> float:
        return asyncio.get_event_loop().time()

    def create_lock(self) -> AsyncioLock:
        return AsyncioLock()

    def create_event(self) -> AsyncioEvent:
        return AsyncioEvent()

    @asynccontextmanager
    async def create_task_group(self) -> AsyncIterator[AsyncioTaskGroup]:
        """Create an asyncio task group."""
        tg = AsyncioTaskGroup()
        async with tg:
            yield tg

    def call_soon_threadsafe(self, callback: Callable):
        """Use asyncio's native call_soon_threadsafe."""
        loop = asyncio.get_event_loop()

        # Handle both sync and async callbacks
        if asyncio.iscoroutinefunction(callback):
            # For async callbacks, create a task
            def wrapper():
                asyncio.create_task(callback())
            loop.call_soon_threadsafe(wrapper)
        else:
            loop.call_soon_threadsafe(callback)

    async def run_sync_in_thread(
        self,
        func: Callable[..., T],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """Run sync function in thread pool."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, func, *args, **kwargs)

    def create_queue(self, max_size: int = 0) -> AsyncioQueue[T]:
        return AsyncioQueue(max_size)
```

### 5. Backend Registry and Access

```python
# src/hother/cancelable/backends/__init__.py
"""
Backend abstraction for asyncio and anyio support.

This module provides automatic backend detection and a unified API
for async operations that works across both asyncio and anyio.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .detection import detect_backend, BackendType

if TYPE_CHECKING:
    from .base import AsyncBackend

# Backend instances (lazy loaded)
_backend_cache: dict[BackendType, AsyncBackend] = {}


def get_backend() -> AsyncBackend:
    """
    Get the current async backend instance.

    Automatically detects whether we're running under asyncio or anyio
    and returns the appropriate backend implementation.

    Returns:
        AsyncBackend instance for the current async library

    Raises:
        RuntimeError: If called outside async context

    Example:
        ```python
        async def my_function():
            backend = get_backend()
            async with backend.create_cancel_scope() as scope:
                await backend.sleep(1.0)
        ```
    """
    backend_type = detect_backend()

    # Lazy load backend
    if backend_type not in _backend_cache:
        if backend_type == "asyncio":
            from .asyncio_backend import AsyncioBackend
            _backend_cache[backend_type] = AsyncioBackend()
        else:  # anyio
            from .anyio_backend import AnyioBackend
            _backend_cache[backend_type] = AnyioBackend()

    return _backend_cache[backend_type]


__all__ = [
    "get_backend",
    "detect_backend",
    "BackendType",
]
```

---

## Migration Strategy

### Phase 1: Foundation (Week 1)

**Priority: CRITICAL BUG FIXES**

1. Create backend abstraction structure:
   - Create `src/hother/cancelable/backends/` directory
   - Implement `base.py` with abstract interfaces
   - Implement `detection.py` with sniffio integration
   - Implement `anyio_backend.py`
   - Implement `asyncio_backend.py`
   - Implement `__init__.py` with `get_backend()`

2. **FIX CRITICAL BUGS:**
   - Fix `timeout.py` to use backend.create_task_group() instead of asyncio.create_task
   - Fix `condition.py` to use backend.create_task_group() and backend.get_cancelled_exc_class()
   - Investigate and fix `composite.py`

3. Update imports:
   - Update `__init__.py` to export backend utilities
   - Add `sniffio` to dependencies

4. Test infrastructure:
   - Create parametrized test fixtures for both backends
   - Add backend detection tests

### Phase 2: Core Components (Week 2)

5. Update `cancellable.py`:
   - Replace `anyio.CancelScope()` with `backend.create_cancel_scope()`
   - Replace `anyio.get_cancelled_exc_class()` with `backend.get_cancelled_exc_class()`
   - Replace `anyio.sleep()` with `backend.sleep()`
   - Replace `anyio.current_time()` with `backend.current_time()`

6. Update `token.py`:
   - Replace `anyio.Event()` with `backend.create_event()`
   - Update thread safety to use `backend.call_soon_threadsafe()`

7. Update `registry.py`:
   - Replace `anyio.Lock()` with `backend.create_lock()`

### Phase 3: Sources (Week 2)

8. Update `base.py`:
   - Update CancelScope type hints to use backend types

9. Update `timeout.py`:
   - Already fixed in Phase 1

10. Update `condition.py`:
    - Already fixed in Phase 1
    - Replace `anyio.to_thread.run_sync()` with `backend.run_sync_in_thread()`

11. Update `signal.py`:
    - Update thread safety to use `backend.call_soon_threadsafe()`

12. Update `composite.py`:
    - Fix any task creation issues

### Phase 4: Utilities (Week 3)

13. Update `anyio_bridge.py`:
    - Keep as anyio-specific implementation
    - Used by AnyioBackend.call_soon_threadsafe()
    - No changes needed (already anyio-specific)

14. Update `streams.py`:
    - Replace anyio operations with backend calls

15. Update `testing.py`:
    - Add backend-aware test utilities

### Phase 5: Integration & Examples (Week 3)

16. Update `integrations/fastapi.py`:
    - Update to use backend abstraction

17. Update all example files:
    - Ensure examples work on both backends
    - Add backend-specific examples if needed

18. Update validation scripts:
    - Keep existing anyio examples
    - Create asyncio equivalents

### Phase 6: Testing & Documentation (Week 4)

19. Comprehensive testing:
    - Run ALL 209 tests on BOTH backends
    - Add new backend-specific tests
    - Test backend detection
    - Test backend switching

20. Update documentation:
    - Add backend section to README
    - Document backend detection
    - Add backend-specific examples
    - Update API docs

21. Performance testing:
    - Benchmark backend abstraction overhead
    - Ensure <1% performance impact

---

## Testing Strategy

### 1. Parametrized Test Fixtures

```python
# tests/conftest.py

import pytest
import anyio
import asyncio
from hother.cancelable.backends import detect_backend

# Parametrize tests to run on both backends
@pytest.fixture(params=["asyncio", "anyio"])
def backend_type(request):
    """Parametrize tests across backends."""
    return request.param

@pytest.fixture
async def backend(backend_type):
    """Get backend instance for current test backend."""
    if backend_type == "asyncio":
        # Set up asyncio context
        from hother.cancelable.backends.asyncio_backend import AsyncioBackend
        return AsyncioBackend()
    else:
        # Set up anyio context
        from hother.cancelable.backends.anyio_backend import AnyioBackend
        return AnyioBackend()
```

### 2. Backend Detection Tests

```python
# tests/unit/test_backend_detection.py

import pytest
import anyio
import asyncio
from hother.cancelable.backends import detect_backend, get_backend
from hother.cancelable.backends.asyncio_backend import AsyncioBackend
from hother.cancelable.backends.anyio_backend import AnyioBackend

@pytest.mark.asyncio
async def test_detect_asyncio_backend():
    """Test backend detection in asyncio context."""
    backend_type = detect_backend()
    assert backend_type == "asyncio"

    backend = get_backend()
    assert isinstance(backend, AsyncioBackend)

@pytest.mark.anyio
async def test_detect_anyio_backend():
    """Test backend detection in anyio context."""
    backend_type = detect_backend()
    assert backend_type == "anyio"

    backend = get_backend()
    assert isinstance(backend, AnyioBackend)
```

### 3. Cross-Backend Feature Tests

All existing tests should be updated to run on both backends:

```python
# tests/unit/test_cancellable.py

import pytest
from hother.cancelable import Cancellable

@pytest.mark.parametrize("backend", ["asyncio", "anyio"])
async def test_timeout_cancellation(backend):
    """Test that timeout works on both backends."""
    # Test will run twice - once with asyncio, once with anyio
    async with Cancellable.with_timeout(0.1) as cancel:
        await cancel.sleep(1.0)

    assert cancel.is_cancelled
    assert cancel.context.cancel_reason == CancellationReason.TIMEOUT
```

---

## Public API Impact

**ZERO API CHANGES** - The public API remains completely unchanged:

```python
# Users continue to use the library exactly as before
from hother.cancelable import Cancellable, CancellationToken

# Works identically on both asyncio and anyio
async with Cancellable.with_timeout(5.0) as cancel:
    await do_work()
```

The backend abstraction is completely internal. Users never need to:
- Import from `backends/`
- Call `get_backend()` or `detect_backend()`
- Configure or select a backend
- Change any existing code

---

## Dependencies

### New Dependencies

```toml
# pyproject.toml
[project]
dependencies = [
    "anyio>=4.0.0",
    "pydantic>=2.0.0",
    "structlog>=23.1.0",
    "sniffio>=1.3.0",  # NEW - for backend detection
]
```

### No Breaking Changes

All existing dependencies remain:
- anyio (still primary backend)
- pydantic (models)
- structlog (logging)
- httpx, fastapi, sqlalchemy (integrations - optional)

---

## Rollout Plan

### Stage 1: Internal Release (Week 4)
- All changes complete
- All tests passing on both backends
- Internal documentation updated
- Team validation

### Stage 2: Beta Release (Week 5)
- Release as `0.2.0-beta1`
- Announce backend support in changelog
- Request community testing
- Monitor for issues

### Stage 3: Stable Release (Week 6)
- Address beta feedback
- Final performance validation
- Release as `0.2.0`
- Update all documentation

---

## Success Metrics

1. **All 209+ existing tests pass on BOTH backends**
2. **Zero public API changes required**
3. **Backend detection works 100% reliably**
4. **Performance overhead < 1%**
5. **No regressions in functionality**
6. **All examples work on both backends**

---

## Risk Analysis

### High Risk Items

1. **AsyncioCancelScope complexity** - Mapping anyio's CancelScope to asyncio requires careful handling of task cancellation and exceptions
   - **Mitigation:** Extensive testing, incremental development

2. **Existing asyncio bugs** - timeout.py and condition.py are currently broken
   - **Mitigation:** Fix immediately in Phase 1 (CRITICAL)

3. **Signal handling differences** - Signal handling may behave differently across backends
   - **Mitigation:** Thorough testing of signal sources

### Medium Risk Items

4. **Thread safety differences** - asyncio.call_soon_threadsafe vs AnyioBridge
   - **Mitigation:** Comprehensive thread safety tests

5. **Performance impact** - Backend abstraction adds indirection
   - **Mitigation:** Benchmark and optimize hotpaths

### Low Risk Items

6. **Documentation updates** - Large documentation update required
   - **Mitigation:** Document as we go

---

## Next Steps

1. **Get approval for this plan**
2. **Start Phase 1 immediately** - Critical bug fixes in timeout.py and condition.py
3. **Set up project tracking** - Create issues for each phase
4. **Begin implementation** - Start with backend abstraction structure

---

## Questions for Review

1. Is the CancelScope mapping for asyncio acceptable, or should we use a different approach?
2. Should we add explicit backend selection (environment variable) or rely solely on sniffio?
3. Should we maintain backward compatibility with the broken asyncio behavior, or fix it immediately?
4. Do we need a migration guide for users (even though API doesn't change)?

---

**Status:** Ready for Review & Implementation
**Priority:** HIGH - Fixes critical bugs, enables dual backend support
**Estimated Effort:** 4 weeks (1 developer)
