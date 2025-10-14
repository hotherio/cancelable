#!/usr/bin/env python3
"""
Pure asyncio example: Cancel operation from another thread.

This demonstrates how to implement thread-safe cancellation using only asyncio.
No anyio dependency.
"""

import asyncio
import threading
import time
from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Optional


@dataclass
class SimpleCancellationToken:
    """Thread-safe cancellation token using asyncio primitives."""

    def __init__(self):
        self.is_cancelled = False
        self.cancelled_at: Optional[datetime] = None
        self.message: Optional[str] = None
        self._event = asyncio.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        """Set the event loop for thread-safe cancellation."""
        self._loop = loop

    def cancel_from_thread(self, message: str = "Cancelled"):
        """Cancel the operation from a separate thread."""
        if self.is_cancelled:
            return False

        self.is_cancelled = True
        self.cancelled_at = datetime.now(UTC)
        self.message = message

        # Schedule the event.set() call in the event loop thread
        if self._loop:
            self._loop.call_soon_threadsafe(self._event.set)

        return True

    async def cancel_async(self, message: str = "Cancelled"):
        """Cancel the operation from async context."""
        if self.is_cancelled:
            return False

        self.is_cancelled = True
        self.cancelled_at = datetime.now(UTC)
        self.message = message
        self._event.set()
        return True

    async def wait_for_cancellation(self):
        """Wait until cancellation is requested."""
        await self._event.wait()

    def check(self):
        """Check if cancelled and raise if so."""
        if self.is_cancelled:
            raise asyncio.CancelledError(self.message)


async def cancellable_operation_with_thread(token: SimpleCancellationToken):
    """Operation that can be cancelled from a thread."""
    print("[Async] Starting operation...")

    try:
        for i in range(10):
            # Check token at each iteration
            token.check()
            await asyncio.sleep(0.5)
            print(f"[Async] Working... {i + 1}/10")

        print("[Async] Operation completed successfully")
        return "completed"

    except asyncio.CancelledError:
        print(f"[Async] Operation was cancelled: {token.message}")
        return "cancelled"


async def main():
    """Main async function demonstrating thread-based cancellation."""
    print("=== Pure Asyncio: Cancel from Thread Example ===\n")

    # Create token and set event loop
    token = SimpleCancellationToken()
    token.set_loop(asyncio.get_event_loop())

    # Create thread that will cancel the operation
    def cancel_from_thread():
        """Thread function that cancels after 2 seconds."""
        time.sleep(2.0)
        print("[Thread] Cancelling operation from thread...")
        success = token.cancel_from_thread("Cancelled from thread")
        print(f"[Thread] Cancel signal sent (success={success})")

    # Start cancellation thread
    cancel_thread = threading.Thread(target=cancel_from_thread, daemon=True)
    cancel_thread.start()

    # Run the cancellable operation
    result = await cancellable_operation_with_thread(token)
    print(f"\n[Main] Operation result: {result}")

    # Wait for thread to complete
    cancel_thread.join(timeout=1.0)
    print("✅ Thread cancellation successful with pure asyncio!")


if __name__ == "__main__":
    asyncio.run(main())
