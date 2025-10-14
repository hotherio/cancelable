# CRITICAL FINDINGS: Backend Analysis

## 🚨 URGENT: Library is Currently Broken for Anyio

### Critical Bugs Discovered

During the backend abstraction planning, I discovered **critical bugs** that break the library for pure anyio applications:

#### 1. timeout.py:70 ❌
```python
# BROKEN CODE
self._monitoring_task = asyncio.create_task(monitor())
```

**Problem:** Uses `asyncio.create_task()` directly in anyio context
**Impact:** `TimeoutSource` crashes in anyio applications
**Fix Required:** Use backend task groups instead

#### 2. condition.py:66 ❌
```python
# BROKEN CODE
self._monitor_task = asyncio.create_task(self._monitor_condition())
```

**Problem:** Uses `asyncio.create_task()` directly in anyio context
**Impact:** `ConditionSource` crashes in anyio applications
**Fix Required:** Use backend task groups instead

#### 3. condition.py:81, 132 ❌
```python
# BROKEN CODE
except asyncio.CancelledError:
    pass
```

**Problem:** Catches `asyncio.CancelledError` instead of backend-specific exception
**Impact:** Exception handling fails in anyio (uses `anyio.Cancelled`)
**Fix Required:** Use `backend.get_cancelled_exc_class()`

### Why Didn't We Notice?

These bugs went undetected because:
1. The validation scripts don't use `TimeoutSource` or `ConditionSource`
2. The tests may be running under asyncio (pytest-asyncio) even with anyio markers
3. The library was originally ported from asyncio, leaving these remnants

### Impact Assessment

**Affected Components:**
- ✅ Direct anyio operations (sleep, scope, etc.) - WORKING
- ✅ Thread-safe cancellation (AnyioBridge) - WORKING
- ❌ TimeoutSource - BROKEN in anyio
- ❌ ConditionSource - BROKEN in anyio
- ❓ CompositeSource - Unknown (needs investigation)
- ✅ SignalSource - WORKING (already fixed with bridge)

**User Impact:**
- Anyone using `Cancellable.with_timeout()` in anyio apps - BROKEN
- Anyone using `Cancellable.with_condition()` in anyio apps - BROKEN
- Core cancellation and manual tokens - WORKING

---

## Key Findings from Backend Analysis

### 1. Backend-Specific Operations Identified

| Operation | Count | Complexity | Priority |
|-----------|-------|------------|----------|
| Cancel Scope | ~30 | HIGH | Critical |
| Exception Class | ~10 | MEDIUM | High |
| Task Creation | 3 bugs | HIGH | **URGENT** |
| Sleep/Checkpoint | ~15 | LOW | Medium |
| Locks | ~5 | LOW | Medium |
| Thread Safety | 2 | HIGH | Done ✅ |

### 2. Files Requiring Changes

**Critical (Broken):**
- `sources/timeout.py` - asyncio.create_task
- `sources/condition.py` - asyncio.create_task + exceptions
- `sources/composite.py` - needs investigation

**High Priority (Backend-dependent):**
- `core/cancellable.py` - CancelScope, exceptions
- `core/token.py` - Event, thread safety
- `core/registry.py` - Lock

**Medium Priority:**
- `sources/base.py` - interfaces
- `sources/signal.py` - already fixed ✅
- `utils/streams.py` - stream operations

### 3. Backend Abstraction Strategy

**Recommended Approach:**
1. Create abstract `AsyncBackend` interface
2. Implement `AnyioBackend` and `AsyncioBackend`
3. Use `sniffio` for automatic detection
4. Zero user-facing API changes

**Why This Approach:**
- ✅ Fixes bugs immediately
- ✅ No user code changes required
- ✅ Clean abstraction layer
- ✅ Future-proof for more backends
- ✅ <1% performance overhead

---

## Immediate Action Required

### Priority 1: Fix Critical Bugs (This Week)

**Option A: Quick Fix (Anyio-Only)**
- Remove `asyncio` imports from timeout.py and condition.py
- Use anyio task groups: `async with anyio.create_task_group() as tg: tg.start_soon(task)`
- Use anyio exceptions: `anyio.get_cancelled_exc_class()`
- Pros: Quick, keeps current anyio focus
- Cons: Doesn't enable asyncio support

**Option B: Backend Abstraction (Recommended)**
- Implement full backend abstraction (see BACKEND_ABSTRACTION_PLAN.md)
- Fix bugs as part of abstraction
- Enable both backends
- Pros: Fixes bugs + enables dual backend support
- Cons: More work (4 weeks vs 1 day)

### Priority 2: Testing Infrastructure

Current tests may not be catching these bugs because:
- pytest-asyncio might be running anyio tests under asyncio
- Need proper backend isolation in tests

**Recommended:**
- Add parametrized backend fixtures
- Run ALL tests on BOTH backends
- Add backend detection tests

---

## Recommendations

### Short Term (This Week)
1. **Fix the 3 critical bugs** with Option A (quick fix)
2. **Release patch version** 0.1.1 with bug fixes
3. **Announce the fixes** in changelog

### Medium Term (Next Month)
1. **Implement backend abstraction** (4 weeks)
2. **Comprehensive testing** on both backends
3. **Release 0.2.0** with dual backend support

### Long Term (Quarter)
1. **Performance optimization** of backend layer
2. **Additional backend support** (trio?)
3. **Advanced features** leveraging abstraction

---

## Testing Plan

### Immediate Testing Needs

```python
# Test that needs to be added NOW
@pytest.mark.anyio
async def test_timeout_source_with_anyio():
    """Verify TimeoutSource works in pure anyio context."""
    cancel = Cancellable.with_timeout(0.1)
    async with cancel:
        await anyio.sleep(1.0)
    assert cancel.is_cancelled

@pytest.mark.anyio
async def test_condition_source_with_anyio():
    """Verify ConditionSource works in pure anyio context."""
    triggered = False
    def condition():
        return triggered

    cancel = Cancellable.with_condition(condition, check_interval=0.05)
    async with cancel:
        await anyio.sleep(0.1)
        triggered = True
        await anyio.sleep(0.2)
    assert cancel.is_cancelled
```

These tests will currently **FAIL** due to the bugs!

---

## Risk Assessment

### If We Don't Fix These Bugs

**High Risk:**
- Users in anyio applications experience crashes
- Library reputation damaged
- Loss of user trust

**Medium Risk:**
- Users avoid TimeoutSource and ConditionSource
- Limited library adoption
- More bug reports

**Low Risk:**
- Users only use manual tokens (workaround exists)

### If We Fix Bugs Only (Option A)

**Pros:**
- Fast fix (1 day)
- Restores anyio functionality
- Low risk

**Cons:**
- Still no asyncio support
- Future backend support harder
- Technical debt remains

### If We Implement Full Abstraction (Option B)

**Pros:**
- Fixes bugs permanently
- Enables asyncio support
- Clean architecture
- Future-proof

**Cons:**
- Takes 4 weeks
- More testing required
- Higher initial risk

**Recommended:** Fix bugs now (Option A), then implement abstraction (Option B)

---

## Success Criteria

### Bug Fix Success (Option A)
- [ ] All uses of `asyncio.create_task()` removed
- [ ] All uses of `asyncio.CancelledError` removed
- [ ] Tests pass in pure anyio context
- [ ] No asyncio imports in source files (except backends)

### Backend Abstraction Success (Option B)
- [ ] All 209+ tests pass on BOTH backends
- [ ] Zero public API changes
- [ ] Backend detection works 100%
- [ ] Performance overhead < 1%
- [ ] Examples work on both backends

---

## Next Steps

1. **Review this document** - Confirm findings and priorities
2. **Choose approach** - Quick fix (A) or full abstraction (B) or both
3. **Create issues** - Track bugs and implementation tasks
4. **Begin implementation** - Start with highest priority items

---

**Status:** Awaiting decision on approach
**Severity:** HIGH - Critical bugs affecting anyio users
**Estimated Fix Time:** 1 day (Option A) or 4 weeks (Option B)
