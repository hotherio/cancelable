#!/usr/bin/env python3
"""
Cancelable library example: Cancel operation from another thread.

This demonstrates how to implement thread-safe cancelation using Cancelable.
"""

import threading
import time

import anyio

from hother.cancelable import Cancelable, CancelationToken
from hother.cancelable.core.exceptions import ManualCancelation


async def cancellable_operation(_: Cancelable, token: CancelationToken) -> str:
    """Operation that can be cancelled from a thread."""
    print("[Async] Starting operation...")

    try:
        for i in range(10):
            # Check if cancelled
            if token.is_cancelled:
                raise anyio.get_cancelled_exc_class()("Cancelled")
            await anyio.sleep(0.5)
            print(f"[Async] Working... {i + 1}/10")

        print("[Async] Operation completed successfully")
        return "completed"

    except (anyio.get_cancelled_exc_class(), ManualCancelation):
        print("[Async] Operation was cancelled")
        return "cancelled"


async def main() -> None:
    """Main async function demonstrating thread-based cancelation."""

    # Create token
    token = CancelationToken()

    # Create thread that will cancel the operation
    def cancel_from_thread() -> None:
        """Thread function that cancels after 2 seconds."""
        time.sleep(2.0)
        print("[Thread] Cancelling operation from thread...")
        token.cancel_sync(message="Cancelled from thread")
        print("[Thread] Cancel signal sent")

    # Start cancelation thread
    cancel_thread = threading.Thread(target=cancel_from_thread, daemon=True)
    cancel_thread.start()

    # Run the cancelable operation
    result = "unknown"
    async with Cancelable.with_token(token) as cancel:
        result = await cancellable_operation(cancel, token)

    print(f"\n[Main] Operation result: {result}")

    # Wait for thread to complete
    cancel_thread.join(timeout=1.0)


if __name__ == "__main__":
    anyio.run(main)
