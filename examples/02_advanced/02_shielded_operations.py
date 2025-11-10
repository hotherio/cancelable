#!/usr/bin/env python3
"""
Shielded operations example.
"""

import asyncio

from hother.cancelable import Cancelable


async def main():
    """Run the example."""

    # Example: Shielding critical operations

    try:
        async with Cancelable.with_timeout(2.0, name="parent_operation") as parent:
            print("  Starting parent operation...")
            await asyncio.sleep(0.5)

            # Shield critical section
            print("  Entering shielded section...")
            async with parent.shield():
                print("  Critical operation started (won't be cancelled)")
                await asyncio.sleep(3.0)  # This exceeds parent timeout but won't be cancelled
                print("  Critical operation completed")

            print("  Back to normal operation")
            await asyncio.sleep(1.0)  # This will be cancelled

        print("  Parent operation completed")

    except asyncio.CancelledError:
        print("  Parent operation was cancelled (timeout expired)")


if __name__ == "__main__":
    asyncio.run(main())
