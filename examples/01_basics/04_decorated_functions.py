#!/usr/bin/env python3
"""
Using the @cancelable decorator example.
"""

# --8<-- [start:imports]

import anyio

from hother.cancelable import Cancelable, cancelable

# --8<-- [end:imports]


# --8<-- [start:decorator]
@cancelable(timeout=2.0, name="decorated_operation")
async def slow_operation(duration: float, cancelable: Cancelable = None) -> str:
    """A slow operation with built-in cancelation."""
    await cancelable.report_progress("Starting slow operation")

    steps = int(duration * 10)
    for i in range(steps):
        await anyio.sleep(0.1)
        if i % 10 == 0:
            await cancelable.report_progress(f"Progress: {(i / steps) * 100:.0f}%")

    await cancelable.report_progress("Operation completed")
    return "Success"


# --8<-- [end:decorator]


# --8<-- [start:main]
async def main() -> None:
    """Run the example."""

    # --8<-- [start:example]
    # Example: Using decorators

    try:
        # This will complete
        result = await slow_operation(1.5)
        print(f"  Result: {result}")

        # This will timeout
        result = await slow_operation(3.0)
        print(f"  Result: {result}")

    except anyio.get_cancelled_exc_class():
        print("  Operation was cancelled!")
    # --8<-- [end:example]


# --8<-- [end:main]


if __name__ == "__main__":
    anyio.run(main)
