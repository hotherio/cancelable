# Phase 2: Backend Abstraction Implementation Plan

## Overview

Transform `hother.cancelable` from anyio-only to dual backend support (asyncio + anyio) with zero API changes.

**Status:** Planning Phase
**Duration:** 4 weeks
**Files to modify:** 19 files
**Tests to update:** 209 tests
**New tests to add:** ~50 backend-specific tests

---

## Epic Breakdown

| Epic | Story Count | Priority | Duration | Dependencies |
|------|-------------|----------|----------|--------------|
| Epic 1: Backend Abstraction Infrastructure | 8 | P0 - Critical | Week 1 | None |
| Epic 2: Core Components Migration | 6 | P0 - Critical | Week 2 | Epic 1 |
| Epic 3: Source Components Migration | 6 | P1 - High | Week 2 | Epic 1, Epic 2 |
| Epic 4: Utility & Integration Migration | 5 | P1 - High | Week 3 | Epic 1 |
| Epic 5: Testing Infrastructure | 7 | P0 - Critical | Week 3 | Epic 2, Epic 3 |
| Epic 6: Documentation & Examples | 5 | P2 - Medium | Week 4 | Epic 5 |
| Epic 7: Performance & Quality Assurance | 5 | P1 - High | Week 4 | Epic 5 |

**Total User Stories:** 42

---

# Epic 1: Backend Abstraction Infrastructure

**Goal:** Create the foundational backend abstraction layer that enables seamless asyncio/anyio interoperability

**Acceptance Criteria:**
- Backend detection works 100% reliably using sniffio
- Abstract interface covers all async primitives used in the library
- Both backend implementations pass unit tests
- Zero performance overhead for backend switching

## User Stories

### Story 1.1: Backend Detection System
**As a** library developer
**I want** automatic backend detection using sniffio
**So that** users never need to configure which backend they're using

**Tasks:**
- [ ] Create `src/hother/cancelable/backends/detection.py`
- [ ] Implement `detect_backend()` using sniffio
- [ ] Define `BackendType = Literal["asyncio", "anyio"]`
- [ ] Add error handling for non-async contexts
- [ ] Add unit tests for detection in both contexts

**Acceptance Criteria:**
- Correctly detects asyncio when running under asyncio
- Correctly detects anyio when running under anyio/trio/curio
- Raises clear error when called outside async context
- Tests pass in both pytest-asyncio and pytest-anyio

**Estimated Effort:** 4 hours

---

### Story 1.2: Abstract Backend Interface
**As a** library architect
**I want** a comprehensive abstract base class defining all backend operations
**So that** both backends implement the same interface consistently

**Tasks:**
- [ ] Create `src/hother/cancelable/backends/base.py`
- [ ] Define `AsyncBackend` ABC with all required methods
- [ ] Define abstract classes: `CancelScope`, `Lock`, `Event`, `TaskGroup`, `Queue`
- [ ] Document each method with clear contracts
- [ ] Add type hints using Python 3.13 features

**Interface Methods:**
- `create_cancel_scope(deadline, shield) -> CancelScope`
- `get_cancelled_exc_class() -> type[BaseException]`
- `sleep(seconds) -> None`
- `current_time() -> float`
- `create_lock() -> Lock`
- `create_event() -> Event`
- `create_task_group() -> TaskGroup`
- `call_soon_threadsafe(callback) -> None`
- `run_sync_in_thread(func, *args, **kwargs) -> T`
- `create_queue(max_size) -> Queue`

**Acceptance Criteria:**
- All abstractions are well-documented
- Type hints are complete and accurate
- Mypy passes with no errors
- Interface covers 100% of library needs

**Estimated Effort:** 8 hours

---

### Story 1.3: Anyio Backend Implementation
**As a** library developer
**I want** a complete anyio backend implementation
**So that** existing anyio users continue to work without changes

**Tasks:**
- [ ] Create `src/hother/cancelable/backends/anyio_backend.py`
- [ ] Implement `AnyioBackend(AsyncBackend)`
- [ ] Implement wrapper classes: `AnyioCancelScope`, `AnyioLock`, `AnyioEvent`, `AnyioTaskGroup`, `AnyioQueue`
- [ ] Integrate with existing `AnyioBridge` for thread safety
- [ ] Add comprehensive unit tests

**Acceptance Criteria:**
- All abstract methods implemented
- Wrapper classes delegate correctly to anyio primitives
- Memory object streams used for queues
- AnyioBridge integration works
- All unit tests pass

**Estimated Effort:** 12 hours

---

### Story 1.4: Asyncio Backend Implementation
**As a** library developer
**I want** a complete asyncio backend implementation
**So that** asyncio users can use the library natively

**Tasks:**
- [ ] Create `src/hother/cancelable/backends/asyncio_backend.py`
- [ ] Implement `AsyncioBackend(AsyncBackend)`
- [ ] Implement `AsyncioCancelScope` mapping anyio's scope to asyncio timeout/cancellation
- [ ] Implement `AsyncioTaskGroup` providing anyio-like structured concurrency
- [ ] Implement wrapper classes for Lock, Event, Queue
- [ ] Handle `call_soon_threadsafe` using loop.call_soon_threadsafe
- [ ] Add comprehensive unit tests

**Special Challenges:**
- CancelScope doesn't exist in asyncio - need to emulate with task.cancel() + timeout
- TaskGroup structured concurrency needs custom implementation
- Must handle both sync and async callbacks in call_soon_threadsafe

**Acceptance Criteria:**
- All abstract methods implemented
- CancelScope behaves like anyio's despite asyncio differences
- TaskGroup provides proper cleanup
- call_soon_threadsafe handles both sync/async callbacks
- All unit tests pass

**Estimated Effort:** 16 hours

---

### Story 1.5: Backend Registry and Access
**As a** library developer
**I want** a simple `get_backend()` function that returns the correct backend
**So that** all library code can access backend primitives uniformly

**Tasks:**
- [ ] Create `src/hother/cancelable/backends/__init__.py`
- [ ] Implement `get_backend() -> AsyncBackend` with lazy loading
- [ ] Add backend caching to avoid repeated detection
- [ ] Export public API: `get_backend`, `detect_backend`, `BackendType`
- [ ] Add comprehensive unit tests

**Acceptance Criteria:**
- `get_backend()` returns correct backend based on context
- Backend instances are cached (singleton per backend type)
- Lazy loading works correctly
- Thread-safe implementation
- Tests verify caching behavior

**Estimated Effort:** 4 hours

---

### Story 1.6: Backend Unit Tests
**As a** QA engineer
**I want** comprehensive unit tests for both backends
**So that** I can verify they behave identically

**Tasks:**
- [ ] Create `tests/unit/backends/test_detection.py`
- [ ] Create `tests/unit/backends/test_anyio_backend.py`
- [ ] Create `tests/unit/backends/test_asyncio_backend.py`
- [ ] Create `tests/unit/backends/test_backend_parity.py`
- [ ] Parametrize tests to run on both backends
- [ ] Test all primitive operations (sleep, lock, event, etc.)

**Test Coverage:**
- Backend detection in both contexts
- All AsyncBackend methods on both implementations
- CancelScope behavior parity
- TaskGroup behavior parity
- Exception handling parity
- Thread safety

**Acceptance Criteria:**
- 100% code coverage for backend modules
- All tests pass on both backends
- Parity tests verify identical behavior
- No flaky tests

**Estimated Effort:** 12 hours

---

### Story 1.7: Add sniffio Dependency
**As a** package maintainer
**I want** sniffio added as a dependency
**So that** backend detection works

**Tasks:**
- [ ] Add `sniffio>=1.3.0` to `pyproject.toml` dependencies
- [ ] Verify no version conflicts
- [ ] Update lockfile with `uv lock`
- [ ] Test installation in clean environment

**Acceptance Criteria:**
- Dependency added to pyproject.toml
- No conflicts with existing dependencies
- Clean install works

**Estimated Effort:** 1 hour

---

### Story 1.8: Backend Exports in Main __init__
**As a** library user
**I want** to optionally import backend utilities
**So that** I can use them for advanced use cases

**Tasks:**
- [ ] Update `src/hother/cancelable/__init__.py`
- [ ] Export `get_backend`, `detect_backend` from backends
- [ ] Update `__all__` list
- [ ] Add to documentation

**Note:** This is optional for users - most won't need it

**Acceptance Criteria:**
- Imports work: `from hother.cancelable import get_backend`
- API documentation updated
- No breaking changes to existing imports

**Estimated Effort:** 2 hours

---

# Epic 2: Core Components Migration

**Goal:** Migrate core library components (`cancellable.py`, `token.py`, `registry.py`) to use backend abstraction

**Acceptance Criteria:**
- Core components work identically on both backends
- No anyio imports in migrated files (except via backend)
- All existing tests pass on both backends
- No API changes

## User Stories

### Story 2.1: Migrate cancellable.py - CancelScope
**As a** library developer
**I want** `Cancellable` to use backend.create_cancel_scope()
**So that** it works on both asyncio and anyio

**Current Usage:** `anyio.CancelScope()` used ~10 times in `cancellable.py`

**Tasks:**
- [ ] Add `backend = get_backend()` at module or method level
- [ ] Replace `anyio.CancelScope()` with `backend.create_cancel_scope()`
- [ ] Replace `anyio.get_cancelled_exc_class()` with `backend.get_cancelled_exc_class()`
- [ ] Update scope usage in `__aenter__` and `__aexit__`
- [ ] Handle `with` statement compatibility

**Files:** `src/hother/cancelable/core/cancellable.py`

**Acceptance Criteria:**
- No direct anyio imports (except type hints if needed)
- All cancellation tests pass on both backends
- CancelScope lifecycle works identically
- Shield functionality works on both backends

**Estimated Effort:** 6 hours

---

### Story 2.2: Migrate cancellable.py - Sleep and Time
**As a** library developer
**I want** sleep and time operations abstracted
**So that** they use the correct backend

**Current Usage:**
- `anyio.sleep()` used for checkpoints
- `anyio.current_time()` used for timeout calculations

**Tasks:**
- [ ] Replace `anyio.sleep(0)` with `await backend.sleep(0)`
- [ ] Replace `anyio.sleep(duration)` with `await backend.sleep(duration)`
- [ ] Replace `anyio.current_time()` with `backend.current_time()`

**Files:** `src/hother/cancelable/core/cancellable.py`

**Acceptance Criteria:**
- Checkpoints work on both backends
- Timing accuracy maintained
- No performance regression

**Estimated Effort:** 2 hours

---

### Story 2.3: Migrate token.py - Event
**As a** library developer
**I want** `CancellationToken` to use backend.create_event()
**So that** async waiting works on both backends

**Current Usage:** `anyio.Event()` in token initialization

**Tasks:**
- [ ] Replace `anyio.Event()` with `backend.create_event()`
- [ ] Ensure `wait_for_cancel()` works on both backends
- [ ] Verify thread-safe event setting via bridge

**Files:** `src/hother/cancelable/core/token.py`

**Acceptance Criteria:**
- Token cancellation works on both backends
- `wait_for_cancel()` behaves identically
- Thread-safe cancellation works

**Estimated Effort:** 3 hours

---

### Story 2.4: Migrate registry.py - Lock
**As a** library developer
**I want** `OperationRegistry` to use backend.create_lock()
**So that** registry operations are thread-safe on both backends

**Current Usage:** `anyio.Lock()` for registry synchronization

**Tasks:**
- [ ] Replace `anyio.Lock()` with `backend.create_lock()`
- [ ] Verify all async context manager usage works
- [ ] Test concurrent registry operations

**Files:** `src/hother/cancelable/core/registry.py`

**Acceptance Criteria:**
- Registry synchronization works on both backends
- No race conditions
- Performance comparable to original

**Estimated Effort:** 3 hours

---

### Story 2.5: Update Core Module Imports
**As a** library developer
**I want** clean imports in core modules
**So that** backend abstraction is consistent

**Tasks:**
- [ ] Review all `import anyio` statements in core/
- [ ] Replace with `from ...backends import get_backend` where needed
- [ ] Update type hints to use backend types
- [ ] Verify mypy passes

**Files:** All files in `src/hother/cancelable/core/`

**Acceptance Criteria:**
- No unnecessary anyio imports
- Type hints are correct
- Mypy happy

**Estimated Effort:** 2 hours

---

### Story 2.6: Core Integration Tests
**As a** QA engineer
**I want** integration tests for core components on both backends
**So that** I can verify they work end-to-end

**Tasks:**
- [ ] Create `tests/integration/test_backend_core.py`
- [ ] Test Cancellable lifecycle on both backends
- [ ] Test token cancellation on both backends
- [ ] Test registry operations on both backends
- [ ] Parametrize tests across backends

**Acceptance Criteria:**
- All integration tests pass on both backends
- Tests cover critical workflows
- No backend-specific failures

**Estimated Effort:** 6 hours

---

# Epic 3: Source Components Migration

**Goal:** Migrate all cancellation sources to use backend abstraction

**Acceptance Criteria:**
- All sources work on both backends
- No direct anyio/asyncio imports in sources
- Existing behavior preserved
- All source tests pass on both backends

## User Stories

### Story 3.1: Migrate timeout.py
**As a** library developer
**I want** TimeoutSource to work on both backends
**So that** timeouts function identically

**Current State:** Already partially migrated in Phase 1 (simplified)

**Tasks:**
- [ ] Verify `backend.current_time()` works for deadline calculation
- [ ] Ensure scope.deadline works on AsyncioCancelScope
- [ ] Test timeout accuracy on both backends

**Files:** `src/hother/cancelable/sources/timeout.py`

**Acceptance Criteria:**
- Timeout accuracy within 10ms on both backends
- Deadline handling works correctly
- triggered flag set properly

**Estimated Effort:** 3 hours

---

### Story 3.2: Migrate condition.py
**As a** library developer
**I want** ConditionSource to use backend task groups
**So that** condition monitoring works on both backends

**Current State:** Uses anyio task groups from Phase 1

**Tasks:**
- [ ] Replace `anyio.create_task_group()` with `backend.create_task_group()`
- [ ] Replace `anyio.sleep()` with `backend.sleep()`
- [ ] Replace `anyio.to_thread.run_sync()` with `backend.run_sync_in_thread()`
- [ ] Replace `anyio.get_cancelled_exc_class()` with `backend.get_cancelled_exc_class()`
- [ ] Test condition checking on both backends

**Files:** `src/hother/cancelable/sources/condition.py`

**Acceptance Criteria:**
- Condition checking works on both backends
- Task group lifecycle correct
- Thread pool execution works
- ResourceConditionSource works

**Estimated Effort:** 5 hours

---

### Story 3.3: Migrate composite.py
**As a** library developer
**I want** CompositeSource to use backend task groups
**So that** multi-source composition works on both backends

**Current State:** Uses anyio task groups from Phase 1

**Tasks:**
- [ ] Replace `anyio.create_task_group()` with `backend.create_task_group()`
- [ ] Replace `anyio.Lock()` with `backend.create_lock()` (for AllOfSource)
- [ ] Replace `anyio.CancelScope()` with `backend.create_cancel_scope()`
- [ ] Test AnyOfSource on both backends
- [ ] Test AllOfSource on both backends

**Files:** `src/hother/cancelable/sources/composite.py`

**Acceptance Criteria:**
- CompositeSource works on both backends
- AnyOfSource triggers correctly
- AllOfSource waits for all sources
- Cleanup handles both backends

**Estimated Effort:** 5 hours

---

### Story 3.4: Migrate signal.py
**As a** library developer
**I want** SignalSource thread safety to use backend abstraction
**So that** signal handling works on both backends

**Current State:** Uses `call_soon_threadsafe` from anyio_bridge

**Tasks:**
- [ ] Update to use `backend.call_soon_threadsafe()`
- [ ] Verify signal handling on asyncio
- [ ] Verify signal handling on anyio
- [ ] Test SIGINT, SIGTERM on both backends

**Files:** `src/hother/cancelable/sources/signal.py`

**Acceptance Criteria:**
- Signal handling works on both backends
- Thread safety maintained
- Clean shutdown on both backends

**Estimated Effort:** 4 hours

---

### Story 3.5: Migrate base.py
**As a** library developer
**I want** CancellationSource base class to use backend types
**So that** all sources have consistent type hints

**Tasks:**
- [ ] Update type hints to use backend CancelScope type
- [ ] Update imports
- [ ] Verify all subclasses still type-check

**Files:** `src/hother/cancelable/sources/base.py`

**Acceptance Criteria:**
- Type hints are backend-agnostic
- Mypy passes
- No breaking changes

**Estimated Effort:** 2 hours

---

### Story 3.6: Source Integration Tests
**As a** QA engineer
**I want** integration tests for all sources on both backends
**So that** I can verify cancellation works identically

**Tasks:**
- [ ] Create `tests/integration/test_backend_sources.py`
- [ ] Test each source type on both backends
- [ ] Test source composition on both backends
- [ ] Parametrize across backends

**Acceptance Criteria:**
- All sources tested on both backends
- Composition tests pass
- No backend-specific bugs

**Estimated Effort:** 6 hours

---

# Epic 4: Utility & Integration Migration

**Goal:** Migrate utility modules and third-party integrations to backend abstraction

**Acceptance Criteria:**
- Utilities work on both backends
- Integrations (httpx, FastAPI, SQLAlchemy) work on both backends
- AnyioBridge remains anyio-specific but used via backend

## User Stories

### Story 4.1: Update anyio_bridge.py Usage
**As a** library developer
**I want** AnyioBridge to be used only by AnyioBackend
**So that** thread safety works correctly on both backends

**Strategy:** Keep anyio_bridge.py as-is (anyio-specific), but:
- AnyioBackend uses it for `call_soon_threadsafe`
- AsyncioBackend uses `loop.call_soon_threadsafe` directly

**Tasks:**
- [ ] Ensure AnyioBridge only imported by AnyioBackend
- [ ] Remove direct AnyioBridge imports from other modules
- [ ] Use `backend.call_soon_threadsafe()` everywhere

**Files:** `src/hother/cancelable/utils/anyio_bridge.py` (no changes)

**Acceptance Criteria:**
- AnyioBridge only used by AnyioBackend
- Thread safety works on both backends
- Existing anyio tests still pass

**Estimated Effort:** 3 hours

---

### Story 4.2: Migrate streams.py
**As a** library developer
**I want** stream utilities to use backend abstraction
**So that** `cancellable_stream` works on both backends

**Current Usage:** Various anyio operations in stream processing

**Tasks:**
- [ ] Replace anyio operations with backend calls
- [ ] Update `cancellable_stream` decorator
- [ ] Test stream processing on both backends

**Files:** `src/hother/cancelable/utils/streams.py`

**Acceptance Criteria:**
- Stream processing works on both backends
- Cancellation during streaming works
- Performance comparable

**Estimated Effort:** 4 hours

---

### Story 4.3: Migrate testing.py
**As a** library developer
**I want** testing utilities to support both backends
**So that** users can test with either backend

**Tasks:**
- [ ] Add backend-aware test helpers
- [ ] Update fixtures to work with both backends
- [ ] Document backend selection for tests

**Files:** `src/hother/cancelable/utils/testing.py`

**Acceptance Criteria:**
- Test helpers work on both backends
- Documentation clear
- Examples provided

**Estimated Effort:** 4 hours

---

### Story 4.4: Migrate FastAPI Integration
**As a** library developer
**I want** FastAPI integration to use backend abstraction
**So that** it works regardless of FastAPI's async backend

**Current Usage:** anyio operations in middleware and dependencies

**Tasks:**
- [ ] Replace anyio operations with backend calls
- [ ] Test with FastAPI on asyncio
- [ ] Test with FastAPI on anyio
- [ ] Update integration tests

**Files:** `src/hother/cancelable/integrations/fastapi.py`

**Acceptance Criteria:**
- FastAPI integration works on both backends
- Middleware functions correctly
- Dependencies inject correctly

**Estimated Effort:** 5 hours

---

### Story 4.5: Update Example Files
**As a** library user
**I want** example files to work on both backends
**So that** I can see how to use the library

**Tasks:**
- [ ] Review all example files
- [ ] Update to use backend abstraction where needed
- [ ] Add note about backend detection
- [ ] Test examples on both backends

**Files:** `src/hother/cancelable/examples/*.py`

**Acceptance Criteria:**
- All examples run on both backends
- No backend-specific code in examples
- Documentation updated

**Estimated Effort:** 4 hours

---

# Epic 5: Testing Infrastructure

**Goal:** Ensure comprehensive test coverage across both backends with parametrized tests

**Acceptance Criteria:**
- All 209 existing tests pass on both backends
- New backend-specific tests added
- Test suite runs efficiently
- CI/CD updated to test both backends

## User Stories

### Story 5.1: Create Parametrized Test Fixtures
**As a** QA engineer
**I want** pytest fixtures that parametrize across backends
**So that** tests run automatically on both asyncio and anyio

**Tasks:**
- [ ] Create `tests/conftest.py` backend fixtures
- [ ] Add `@pytest.fixture(params=["asyncio", "anyio"])`
- [ ] Create `backend_type` fixture
- [ ] Create `backend` fixture that returns actual backend instance
- [ ] Document fixture usage

**Example:**
```python
@pytest.fixture(params=["asyncio", "anyio"])
def backend_type(request):
    return request.param

@pytest.fixture
async def backend(backend_type):
    if backend_type == "asyncio":
        return AsyncioBackend()
    else:
        return AnyioBackend()
```

**Acceptance Criteria:**
- Fixtures work with pytest-asyncio and pytest-anyio
- Tests can be parametrized easily
- Clear documentation

**Estimated Effort:** 4 hours

---

### Story 5.2: Parametrize Existing Tests
**As a** QA engineer
**I want** all existing tests to run on both backends
**So that** we verify identical behavior

**Tasks:**
- [ ] Update `tests/unit/test_cancellable.py` to use `backend` fixture
- [ ] Update `tests/unit/test_token.py` to use `backend` fixture
- [ ] Update `tests/unit/test_sources/*.py` to use `backend` fixture
- [ ] Update integration tests to use `backend` fixture
- [ ] Ensure 209 tests * 2 backends = 418 test executions

**Acceptance Criteria:**
- All tests parametrized
- Tests pass on both backends
- No backend-specific failures
- Test execution time reasonable (<5 min total)

**Estimated Effort:** 12 hours

---

### Story 5.3: Add Backend-Specific Tests
**As a** QA engineer
**I want** tests that verify backend-specific behavior
**So that** edge cases are covered

**New Tests:**
- AsyncioCancelScope deadline handling
- AsyncioTaskGroup cleanup
- Asyncio call_soon_threadsafe with coroutines
- Backend detection edge cases
- Backend switching scenarios

**Tasks:**
- [ ] Create `tests/unit/backends/test_asyncio_specific.py`
- [ ] Create `tests/unit/backends/test_anyio_specific.py`
- [ ] Test edge cases for each backend
- [ ] Aim for ~50 new tests

**Acceptance Criteria:**
- Edge cases covered
- Backend-specific behavior verified
- All new tests pass

**Estimated Effort:** 8 hours

---

### Story 5.4: Backend Parity Tests
**As a** QA engineer
**I want** tests that explicitly verify both backends behave identically
**So that** we catch behavioral differences

**Tasks:**
- [ ] Create `tests/unit/backends/test_parity.py`
- [ ] Test identical timing behavior
- [ ] Test identical exception handling
- [ ] Test identical cancellation propagation
- [ ] Compare results from same operation on both backends

**Acceptance Criteria:**
- Parity verified for all primitives
- Tests fail if backends diverge
- Clear failure messages

**Estimated Effort:** 6 hours

---

### Story 5.5: Performance Regression Tests
**As a** QA engineer
**I want** performance tests on both backends
**So that** we detect performance regressions

**Tasks:**
- [ ] Update `tests/performance/test_overhead.py`
- [ ] Benchmark backend abstraction overhead
- [ ] Compare asyncio vs anyio performance
- [ ] Set performance thresholds
- [ ] Document acceptable overhead (<1%)

**Acceptance Criteria:**
- Performance benchmarks run on both backends
- Overhead < 1% vs direct usage
- No significant performance regression
- CI can run performance tests

**Estimated Effort:** 6 hours

---

### Story 5.6: Update CI/CD Configuration
**As a** DevOps engineer
**I want** CI to test both backends
**So that** we catch backend-specific issues early

**Tasks:**
- [ ] Update GitHub Actions workflow
- [ ] Add matrix testing for backends
- [ ] Test on Python 3.12 and 3.13
- [ ] Update test reporting
- [ ] Add backend coverage reporting

**Files:** `.github/workflows/*.yml`

**Acceptance Criteria:**
- CI runs tests on both backends
- Matrix includes Python versions
- Test results clearly show backend
- Coverage reports include both backends

**Estimated Effort:** 4 hours

---

### Story 5.7: Test Documentation
**As a** developer
**I want** clear documentation on testing with different backends
**So that** I can write backend-agnostic tests

**Tasks:**
- [ ] Create `docs/testing.md`
- [ ] Document fixture usage
- [ ] Provide test examples
- [ ] Explain backend selection
- [ ] Document common pitfalls

**Acceptance Criteria:**
- Clear testing guide
- Examples for both backends
- Troubleshooting section

**Estimated Effort:** 3 hours

---

# Epic 6: Documentation & Examples

**Goal:** Comprehensive documentation covering dual backend support

**Acceptance Criteria:**
- Users understand how backend detection works
- Examples demonstrate both backends
- API docs updated
- Migration guide provided

## User Stories

### Story 6.1: Backend Detection Documentation
**As a** library user
**I want** documentation explaining how backend detection works
**So that** I understand what happens at runtime

**Tasks:**
- [ ] Create `docs/backends.md`
- [ ] Explain automatic detection
- [ ] Document sniffio usage
- [ ] Provide examples of detection
- [ ] Explain when detection happens
- [ ] Document edge cases

**Sections:**
- How It Works
- Supported Backends
- Detection Algorithm
- Examples
- Troubleshooting

**Acceptance Criteria:**
- Clear, concise documentation
- Examples for both backends
- Edge cases covered

**Estimated Effort:** 4 hours

---

### Story 6.2: Update API Documentation
**As a** library user
**I want** updated API docs reflecting backend support
**So that** I know which features work where

**Tasks:**
- [ ] Review all docstrings
- [ ] Add backend compatibility notes where relevant
- [ ] Update module-level docs
- [ ] Regenerate API documentation
- [ ] Add backend section to main docs

**Acceptance Criteria:**
- All docstrings accurate
- Backend compatibility clear
- API docs build successfully

**Estimated Effort:** 6 hours

---

### Story 6.3: Create Backend-Specific Examples
**As a** library user
**I want** examples showing usage with both backends
**So that** I can see how to use my preferred backend

**Tasks:**
- [ ] Create `examples/asyncio_example.py`
- [ ] Create `examples/anyio_example.py`
- [ ] Show timeout, condition, signal on both
- [ ] Add README explaining examples
- [ ] Test all examples

**Acceptance Criteria:**
- Examples work on specified backend
- Clear comments explaining differences
- README guides users

**Estimated Effort:** 5 hours

---

### Story 6.4: Update README
**As a** library user
**I want** the README to mention backend support
**So that** I know this is a key feature

**Tasks:**
- [ ] Add "Backend Support" section
- [ ] Update feature list
- [ ] Add backend detection example
- [ ] Update installation instructions
- [ ] Add badge/note about dual backend

**Acceptance Criteria:**
- Backend support prominent
- Examples updated
- Installation clear

**Estimated Effort:** 2 hours

---

### Story 6.5: Create Migration Guide (Phase 1 → Phase 2)
**As a** existing user
**I want** a migration guide from 0.1.1 to 0.2.0
**So that** I know what changed (even if nothing for me)

**Tasks:**
- [ ] Create `docs/migration_0.2.md`
- [ ] Explain "zero API changes"
- [ ] Note new features (asyncio support)
- [ ] List internal changes
- [ ] Provide troubleshooting

**Sections:**
- What Changed
- Do I Need to Change My Code? (No!)
- New Features
- Internal Changes
- Troubleshooting

**Acceptance Criteria:**
- Clear message: no code changes needed
- New features explained
- Troubleshooting provided

**Estimated Effort:** 3 hours

---

# Epic 7: Performance & Quality Assurance

**Goal:** Ensure production-ready quality with comprehensive validation

**Acceptance Criteria:**
- All tests pass on both backends
- Performance overhead < 1%
- No memory leaks
- Clean code quality metrics
- Ready for 0.2.0 release

## User Stories

### Story 7.1: Performance Benchmarking
**As a** performance engineer
**I want** comprehensive benchmarks comparing backends
**So that** we understand performance characteristics

**Tasks:**
- [ ] Benchmark context manager overhead
- [ ] Benchmark cancellation latency
- [ ] Benchmark stream processing
- [ ] Benchmark registry operations
- [ ] Compare asyncio vs anyio vs direct usage
- [ ] Document results

**Metrics:**
- Overhead vs direct asyncio: < 1%
- Overhead vs direct anyio: < 1%
- Asyncio vs anyio difference: documented
- Latency for cancellation: < 1ms

**Acceptance Criteria:**
- Benchmarks run successfully
- Results documented
- Performance acceptable
- No regressions from Phase 1

**Estimated Effort:** 8 hours

---

### Story 7.2: Memory Leak Testing
**As a** reliability engineer
**I want** memory leak tests on both backends
**So that** we ensure no resource leaks

**Tasks:**
- [ ] Use `tracemalloc` to track memory
- [ ] Test long-running operations
- [ ] Test repeated cancellations
- [ ] Test task group cleanup
- [ ] Document memory usage patterns

**Scenarios:**
- 10,000 cancellations in sequence
- 1,000 concurrent operations
- Repeated start/stop of sources
- Long-running condition checking

**Acceptance Criteria:**
- No memory growth over time
- Proper cleanup verified
- Tests pass on both backends

**Estimated Effort:** 6 hours

---

### Story 7.3: Code Quality Review
**As a** code reviewer
**I want** clean, maintainable code
**So that** future changes are easy

**Tasks:**
- [ ] Run `ruff check` on all new code
- [ ] Run `mypy` with strict settings
- [ ] Review all type hints
- [ ] Check for code duplication
- [ ] Ensure consistent style
- [ ] Add missing docstrings

**Quality Metrics:**
- 100% type hint coverage
- 0 ruff errors
- 0 mypy errors
- < 5% code duplication
- All public APIs documented

**Acceptance Criteria:**
- All quality checks pass
- Code is maintainable
- Documentation complete

**Estimated Effort:** 6 hours

---

### Story 7.4: Integration Testing Suite
**As a** QA engineer
**I want** end-to-end integration tests
**So that** we verify real-world scenarios

**Tasks:**
- [ ] Create `tests/integration/test_backend_e2e.py`
- [ ] Test real HTTP operations with both backends
- [ ] Test real database operations with both backends
- [ ] Test complex cancellation scenarios
- [ ] Test hierarchical operations
- [ ] Document test scenarios

**Real-World Scenarios:**
- HTTP download with timeout on both backends
- Database transaction with cancellation
- Multi-stage pipeline with mixed sources
- Parent-child cancellation hierarchy
- Signal-based shutdown

**Acceptance Criteria:**
- All scenarios pass on both backends
- Real external dependencies used
- Scenarios documented

**Estimated Effort:** 8 hours

---

### Story 7.5: Release Preparation
**As a** release manager
**I want** all release artifacts prepared
**So that** we can ship 0.2.0

**Tasks:**
- [ ] Update `pyproject.toml` version to 0.2.0
- [ ] Finalize CHANGELOG.md
- [ ] Build documentation site
- [ ] Create release notes
- [ ] Test package build
- [ ] Prepare PyPI release

**Acceptance Criteria:**
- Version updated
- CHANGELOG complete
- Documentation built
- Package builds successfully
- Release notes ready

**Estimated Effort:** 4 hours

---

# Dependencies and Schedule

## Week 1: Foundation
- **Epic 1:** Backend Abstraction Infrastructure (40 hours)
- **Deliverables:** Backend abstraction layer complete, both implementations working

## Week 2: Core Migration
- **Epic 2:** Core Components Migration (22 hours)
- **Epic 3:** Source Components Migration (25 hours)
- **Deliverables:** Core and source components migrated, tests passing

## Week 3: Integration and Testing
- **Epic 4:** Utility & Integration Migration (20 hours)
- **Epic 5:** Testing Infrastructure (43 hours)
- **Deliverables:** All components migrated, comprehensive test suite

## Week 4: Polish and Release
- **Epic 6:** Documentation & Examples (20 hours)
- **Epic 7:** Performance & QA (32 hours)
- **Deliverables:** Documentation complete, 0.2.0 ready to ship

**Total Estimated Effort:** 202 hours (approximately 4-5 weeks for 1 developer)

---

# Success Metrics

## Must Have (P0)
- ✅ All 209 existing tests pass on both backends
- ✅ Zero breaking API changes
- ✅ Backend detection 100% reliable
- ✅ Performance overhead < 1%

## Should Have (P1)
- ✅ 50+ new backend-specific tests
- ✅ Comprehensive documentation
- ✅ All examples work on both backends
- ✅ CI tests both backends

## Nice to Have (P2)
- ✅ Performance comparisons documented
- ✅ Migration guide polished
- ✅ Advanced usage examples

---

# Risk Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| AsyncioCancelScope behavior differs from anyio | High | High | Extensive parity testing, accept minor differences with documentation |
| Performance regression | Medium | High | Continuous benchmarking, optimize hotpaths |
| Test suite complexity | High | Medium | Clear fixtures, good documentation, parametrization |
| Edge cases in backend switching | Medium | Medium | Comprehensive edge case tests, user feedback |
| Breaking changes introduced accidentally | Low | Critical | Extensive integration tests, API compatibility tests |

---

# Next Actions

1. **Review this plan** - Validate epic breakdown and story details
2. **Refine estimates** - Adjust based on team capacity
3. **Create project board** - Set up tracking (GitHub Projects, Jira, etc.)
4. **Assign stories** - Allocate to team members
5. **Begin Epic 1** - Start with backend abstraction infrastructure

