#!/usr/bin/env python3
"""
Using the with_timeout helper example.
"""

import asyncio

from hother.cancelable import with_timeout


async def main() -> None:
    """Run the example."""

    # Example: Using the with_timeout helper

    async def fetch_data() -> dict[str, str]:
        """Simulate data fetching."""
        await asyncio.sleep(1.0)
        return {"data": "example"}

    try:
        # This will succeed
        result = await with_timeout(2.0, fetch_data())
        print(f"  Success: {result}")

        # This will timeout
        result = await with_timeout(0.5, fetch_data())
        print(f"  Success: {result}")

    except asyncio.CancelledError:
        print("  Operation timed out!")


if __name__ == "__main__":
    asyncio.run(main())
