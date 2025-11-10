#!/usr/bin/env python3
"""
Cancelable example: Cancel operation from another async task.

This demonstrates how to implement task-to-task cancelation using cancelable.
Uses anyio for async operations.
"""

import anyio

from hother.cancelable import Cancelable, CancelationToken
from hother.cancelable.core.models import CancelationReason


async def worker_task(token: CancelationToken):
    """Worker task that monitors cancelation token."""
    print("[Worker] Starting work...")

    try:
        async with Cancelable.with_token(token, name="worker_task"):
            for i in range(10):
                await anyio.sleep(0.5)
                print(f"[Worker] Processing item {i + 1}/10")

            print("[Worker] Work completed successfully")

    except anyio.get_cancelled_exc_class():
        print(f"[Worker] Caught cancelation: {token.message}")


async def canceller_task(token: CancelationToken):
    """Task that cancels the worker after 2 seconds."""
    await anyio.sleep(2.0)
    print("[Canceller] Sending cancel signal...")
    await token.cancel(reason=CancelationReason.MANUAL, message="Cancelled by canceller task")


async def main():
    """Main function demonstrating various cancelation patterns."""
    # Example 1: Cancel from async task
    print("=== Cancelable: Cancel from Async Task Example ===\n")

    # Create shared token
    token = CancelationToken()

    # Run both tasks concurrently
    async with anyio.create_task_group() as tg:
        tg.start_soon(worker_task, token)
        tg.start_soon(canceller_task, token)

    # Example 2: Direct token cancelation
    print("\n=== Cancelable: Direct Token Cancelation ===\n")

    token = CancelationToken()

    async def worker():
        """Worker that will be cancelled."""
        try:
            async with Cancelable.with_token(token, name="direct_cancel_worker"):
                for i in range(10):
                    await anyio.sleep(0.5)
                    print(f"[Worker] Working... {i + 1}/10")
                print("[Worker] Completed")
        except anyio.get_cancelled_exc_class():
            print("[Worker] Task was cancelled")

    # Create task and cancel after 2 seconds
    async with anyio.create_task_group() as tg:
        tg.start_soon(worker)

        # Cancel after 2 seconds
        await anyio.sleep(2.0)
        print("[Main] Cancelling task...")
        await token.cancel(reason=CancelationReason.MANUAL, message="Direct cancelation")


if __name__ == "__main__":
    anyio.run(main)
