#!/usr/bin/env python3
"""
Pure asyncio example: Cancel operation from another async task.

This demonstrates how to implement task-to-task cancellation using only asyncio.
No anyio dependency.
"""

import asyncio
from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Optional


@dataclass
class SimpleCancellationToken:
    """Simple cancellation token using asyncio primitives."""

    def __init__(self):
        self.is_cancelled = False
        self.cancelled_at: Optional[datetime] = None
        self.message: Optional[str] = None
        self._event = asyncio.Event()

    async def cancel(self, message: str = "Cancelled"):
        """Cancel the operation."""
        if self.is_cancelled:
            return False

        self.is_cancelled = True
        self.cancelled_at = datetime.now(UTC)
        self.message = message
        self._event.set()

        print(f"[Token] Cancelled: {message}")
        return True

    async def wait_for_cancellation(self):
        """Wait until cancellation is requested."""
        await self._event.wait()

    def check(self):
        """Check if cancelled and raise if so."""
        if self.is_cancelled:
            raise asyncio.CancelledError(self.message)


async def worker_task(token: SimpleCancellationToken):
    """Worker task that monitors cancellation token."""
    print("[Worker] Starting work...")

    # Get reference to this task so monitor can cancel it
    worker = asyncio.current_task()

    # Create monitoring task
    async def monitor_token():
        await token.wait_for_cancellation()
        # Cancel the worker task
        if worker:
            worker.cancel()

    monitor_task = asyncio.create_task(monitor_token())

    try:
        for i in range(10):
            await asyncio.sleep(0.5)
            print(f"[Worker] Processing item {i + 1}/10")

        print("[Worker] Work completed successfully")
        return "completed"

    except asyncio.CancelledError:
        print(f"[Worker] Caught cancellation: {token.message}")
        return "cancelled"
    finally:
        monitor_task.cancel()
        try:
            await monitor_task
        except asyncio.CancelledError:
            pass


async def canceller_task(token: SimpleCancellationToken):
    """Task that cancels the worker after 2 seconds."""
    await asyncio.sleep(2.0)
    print("[Canceller] Sending cancel signal...")
    await token.cancel("Cancelled by canceller task")


async def main():
    """Main function demonstrating async task cancellation."""
    print("=== Pure Asyncio: Cancel from Async Task Example ===\n")

    # Create shared token
    token = SimpleCancellationToken()

    # Run both tasks concurrently
    worker = asyncio.create_task(worker_task(token))
    canceller = asyncio.create_task(canceller_task(token))

    # Wait for both to complete
    results = await asyncio.gather(worker, canceller, return_exceptions=True)
    print(f"\n[Main] Worker result: {results[0]}")

    print("✅ Async task cancellation successful with pure asyncio!")


async def example_timeout_cancellation():
    """Example showing timeout-based cancellation with asyncio.timeout."""
    print("\n=== Pure Asyncio: Timeout Cancellation ===\n")

    async def long_operation():
        """Operation that takes too long."""
        try:
            for i in range(10):
                await asyncio.sleep(0.5)
                print(f"[Operation] Working... {i + 1}/10")
            return "completed"
        except asyncio.CancelledError:
            print("[Operation] Cancelled due to timeout")
            raise

    # Use asyncio.timeout (Python 3.11+) or asyncio.wait_for
    try:
        import sys
        if sys.version_info >= (3, 11):
            async with asyncio.timeout(2.0):
                result = await long_operation()
        else:
            result = await asyncio.wait_for(long_operation(), timeout=2.0)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        print("[Main] Operation timed out as expected")

    print("✅ Timeout cancellation successful!")


async def example_task_cancellation():
    """Example showing direct task cancellation."""
    print("\n=== Pure Asyncio: Direct Task Cancellation ===\n")

    async def worker():
        """Worker that will be cancelled."""
        try:
            for i in range(10):
                await asyncio.sleep(0.5)
                print(f"[Worker] Working... {i + 1}/10")
            return "completed"
        except asyncio.CancelledError:
            print("[Worker] Task was cancelled")
            raise

    # Create and cancel task
    task = asyncio.create_task(worker())

    # Cancel after 2 seconds
    await asyncio.sleep(2.0)
    print("[Main] Cancelling task...")
    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        print("[Main] Task cancelled successfully")

    print("✅ Direct task cancellation successful!")


if __name__ == "__main__":
    asyncio.run(main())
    asyncio.run(example_timeout_cancellation())
    asyncio.run(example_task_cancellation())
