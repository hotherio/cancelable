"""
Stream processing utilities for async operations.

This module provides tools for simulating and testing cancellable stream processing:

- **StreamConfig**: Configuration for stream simulation behavior
- **simulate_stream**: Simulate realistic network streams with bursts, stalls, and jitter

The simulator is useful for:
- Testing cancellable stream processing
- Demonstrating async cancellation patterns
- Simulating real-world network conditions (latency, jitter, stalls)

Example:
    ```python
    from hother.cancelable import Cancelable
    from hother.cancelable.streaming import StreamConfig
    from hother.cancelable.streaming.simulator import simulate_stream

    config = StreamConfig(base_delay=0.1, stall_probability=0.2)

    async with Cancelable.with_timeout(5.0) as cancel:
        async for event in simulate_stream("Hello world", config, cancel):
            if event["type"] == "data":
                print(event["chunk"], end="")
    ```
"""

# Import from simulator config
from .simulator.config import StreamConfig

__all__ = [
    # Config
    "StreamConfig",
]
