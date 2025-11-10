"""
Cancellation source implementations.

This module provides various ways to trigger cancellation of async operations:

- **CancellationSource**: Abstract base class for all cancellation sources
- **TimeoutSource**: Cancel operations after a specified time period
- **SignalSource**: Cancel operations when Unix signals are received (SIGTERM, SIGINT, etc.)
- **ConditionSource**: Cancel operations when a predicate function returns True
- **TokenSource**: Wrap a CancellationToken as a cancellation source
- **CompositeSource / AnyOfSource**: Combine multiple sources with OR logic (any-of)
- **AllOfSource**: Combine multiple sources with AND logic (all-of)

Example:
    ```python
    from hother.cancelable import Cancelable
    from hother.cancelable.sources import TimeoutSource, SignalSource

    # Create with timeout source
    async with Cancelable.with_timeout(30.0) as cancel:
        await long_operation()

    # Create with signal source
    async with Cancelable.with_signal(signal.SIGTERM) as cancel:
        await server_task()
    ```
"""

from .base import CancelationSource
from .composite import AllOfSource, AnyOfSource, CompositeSource
from .condition import ConditionSource, ResourceConditionSource
from .signal import SignalSource
from .timeout import TimeoutSource

__all__ = [
    # Base
    "CancelationSource",
    # Individual sources
    "TimeoutSource",
    "SignalSource",
    "ConditionSource",
    "ResourceConditionSource",
    # Composite sources
    "CompositeSource",
    "AnyOfSource",
    "AllOfSource",
]
