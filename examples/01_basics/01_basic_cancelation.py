#!/usr/bin/env python3
"""
Basic cancelable context manager usage.
"""

# --8<-- [start:imports]
import anyio

from hother.cancelable import Cancelable

# --8<-- [end:imports]


# --8<-- [start:main]
async def main() -> None:
    """Run the example."""
    # --8<-- [start:example]
    # Example: Basic cancelable context manager
    async with Cancelable(name="basic_example") as cancel:
        # Report progress
        await cancel.report_progress("Starting operation")

        # Do some work
        for i in range(5):
            await cancel.report_progress(f"Step {i + 1}/5")
            await anyio.sleep(0.2)

        await cancel.report_progress("Operation completed")

        print(f"  Operation ID: {cancel.context.id}")
        print(f"  Final status: {cancel.context.status.value}")
        print(f"  Duration: {(cancel.context.duration.total_seconds() if cancel.context.duration else 0.0):.2f}s")
    # --8<-- [end:example]


# --8<-- [end:main]


if __name__ == "__main__":
    anyio.run(main)
