# Performance Considerations

Understanding the performance characteristics and overhead of Cancelable.

## Overhead Analysis

Cancelable adds minimal overhead to async operations:

### Baseline Overhead

- **Context manager entry/exit**: < 1μs
- **Registry operations**: < 5μs
- **Progress reporting**: < 10μs per report
- **Source monitoring**: Depends on check interval

### Benchmarks

Typical overhead compared to pure asyncio:

```python
# Pure asyncio
async with asyncio.timeout(30):
    await operation()  # Baseline

# Cancelable (single source)
async with Cancelable.with_timeout(30.0):
    await operation()  # < 1% overhead

# Cancelable (multiple sources)
async with Cancelable.combine([...]):
    await operation()  # < 2% overhead
```

## Optimization Tips

### Limit Progress Reporting

```python
# ❌ Too frequent - high overhead
for i in range(1_000_000):
    await process(i)
    await cancel.report_progress(...)  # Million calls!

# ✅ Good frequency
for i in range(1_000_000):
    await process(i)
    if i % 1000 == 0:
        await cancel.report_progress(...)  # Thousand calls
```

### Choose Appropriate Check Intervals

```python
# ❌ Too frequent - wastes CPU
ConditionSource(check_disk_space, check_interval=0.01)

# ✅ Reasonable interval
ConditionSource(check_disk_space, check_interval=5.0)
```

### Disable Auto-Registration

Only if registry monitoring is not needed:

```python
# Saves ~5μs per operation
async with Cancelable(auto_register=False) as cancel:
    await operation()
```

## Memory Usage

### Registry Memory

Each registered operation uses ~1KB:

- Small applications: Negligible (< 100 ops = < 100KB)
- Large applications: Monitor with cleanup

### Cleanup

Registry auto-cleans completed operations. For long-running apps:

```python
# Periodic cleanup in production
registry = OperationRegistry.get_instance()
registry.cleanup_completed()  # If needed
```

## Production Recommendations

### Do

- ✅ Use appropriate check intervals (1-10s typical)
- ✅ Report progress at milestones (every 100-1000 items)
- ✅ Monitor registry size in long-running apps
- ✅ Profile your specific use case

### Don't

- ❌ Don't report progress on every iteration
- ❌ Don't use sub-100ms check intervals
- ❌ Don't create excessive nested hierarchies
- ❌ Don't keep references to completed operations

## Profiling

Measure Cancelable overhead in your application:

```python
import time

async def benchmark():
    # Without Cancelable
    start = time.perf_counter()
    await operation()
    baseline = time.perf_counter() - start

    # With Cancelable
    start = time.perf_counter()
    async with Cancelable.with_timeout(30.0) as cancel:
        await operation()
    with_cancel = time.perf_counter() - start

    overhead = ((with_cancel - baseline) / baseline) * 100
    print(f"Overhead: {overhead:.2f}%")
```