# Cancellation Sources

Cancellation sources provide different ways to trigger cancellation of async operations.

## Base Source

### CancellationSource

Abstract base class for all cancellation sources.

::: hother.cancelable.sources.base.CancellationSource
    options:
      show_root_heading: true
      members_order: source
      show_inheritance: true

## Built-in Sources

### TimeoutSource

Cancels operations after a specified time period.

::: hother.cancelable.sources.timeout.TimeoutSource
    options:
      show_root_heading: true
      members_order: source
      show_inheritance: true

### SignalSource

Cancels operations when Unix signals are received (e.g., SIGTERM, SIGINT).

::: hother.cancelable.sources.signal.SignalSource
    options:
      show_root_heading: true
      members_order: source
      show_inheritance: true

### ConditionSource

Cancels operations when a predicate function returns True.

::: hother.cancelable.sources.condition.ConditionSource
    options:
      show_root_heading: true
      members_order: source
      show_inheritance: true

### ResourceConditionSource

Specialized condition source for monitoring system resources (CPU, memory).

::: hother.cancelable.sources.condition.ResourceConditionSource
    options:
      show_root_heading: true
      members_order: source
      show_inheritance: true

## Composite Sources

Composite sources allow combining multiple cancellation sources with different logic:

### OR vs AND Logic Comparison

| Feature | CompositeSource / AnyOfSource | AllOfSource |
|---------|-------------------------------|-------------|
| **Trigger Logic** | Cancels when **ANY** source triggers | Cancels when **ALL** sources trigger |
| **Use Case** | Safety nets, failsafes, OR conditions | Requirements, gates, AND conditions |
| **Example** | Timeout OR manual cancel OR signal | Minimum time AND target count |
| **Thread Safety** | ✅ Yes | ✅ Yes (with `anyio.Lock()`) |
| **Typical Usage** | `Cancelable.combine()` | Manual construction with `AllOfSource([...])` |

### Usage Examples

**OR Logic (Any-Of) - Default:**
```python
from hother.cancelable.sources.composite import CompositeSource
from hother.cancelable.sources.timeout import TimeoutSource
from hother.cancelable.sources.signal import SignalSource

# Cancels when timeout OR signal (whichever comes first)
or_source = CompositeSource([
    TimeoutSource(timeout=60.0),
    SignalSource(signal.SIGTERM)
])
```

**AND Logic (All-Of) - Require All:**
```python
from hother.cancelable.sources.composite import AllOfSource
from hother.cancelable.sources.timeout import TimeoutSource
from hother.cancelable.sources.condition import ConditionSource

# Cancels only when BOTH timeout AND condition are met
and_source = AllOfSource([
    TimeoutSource(timeout=60.0),
    ConditionSource(lambda: items_processed >= 100, 1.0)
])
```

### CompositeSource

Combines multiple cancellation sources into a single source (any-of logic).

::: hother.cancelable.sources.composite.CompositeSource
    options:
      show_root_heading: true
      members_order: source
      show_inheritance: true

### AnyOfSource

Alias for CompositeSource - cancels when any source triggers.

::: hother.cancelable.sources.composite.AnyOfSource
    options:
      show_root_heading: true
      members_order: source
      show_inheritance: true

### AllOfSource

Cancels when all sources have triggered (all-of logic).

::: hother.cancelable.sources.composite.AllOfSource
    options:
      show_root_heading: true
      members_order: source
      show_inheritance: true
