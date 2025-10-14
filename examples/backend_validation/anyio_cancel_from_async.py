#!/usr/bin/env python3
"""
Example: Cancel anyio operation from another async task using current library.

This demonstrates that the current anyio-based implementation can handle
cancellation signals from a separate async task.
"""

import anyio

from hother.cancelable import Cancellable, CancellationToken, CancellationReason


async def main():
    """Main async function demonstrating async task cancellation."""
    print("=== Anyio: Cancel from Async Task Example ===\n")

    # Create a shared cancellation token
    token = CancellationToken()

    async def worker_task():
        """Worker task that will be cancelled."""
        try:
            async with Cancellable.with_token(token, name="worker") as cancel:
                cancel.on_cancel(lambda ctx: print(f"[Worker] Cancelled: {ctx.cancel_reason}"))

                print("[Worker] Starting work...")
                for i in range(10):
                    await anyio.sleep(0.5)
                    print(f"[Worker] Processing item {i + 1}/10")

                print("[Worker] Work completed successfully")
                return "completed"

        except anyio.get_cancelled_exc_class():
            print(f"[Worker] Caught cancellation exception")
            print(f"[Worker] Status: {cancel.context.status}")
            print(f"[Worker] Reason: {cancel.context.cancel_reason}")
            return "cancelled"

    async def canceller_task():
        """Task that cancels the worker after 2 seconds."""
        await anyio.sleep(2.0)
        print("[Canceller] Sending cancel signal...")
        await token.cancel(CancellationReason.MANUAL, "Cancelled by canceller task")
        print("[Canceller] Cancel signal sent")

    # Run both tasks concurrently
    async with anyio.create_task_group() as tg:
        tg.start_soon(worker_task)
        tg.start_soon(canceller_task)

    print("\n✅ Async task cancellation successful!")


async def example_cancel_parent_child():
    """Example showing parent-child cancellation."""
    print("\n=== Anyio: Parent-Child Cancellation ===\n")

    try:
        async with Cancellable.with_timeout(2.0, name="parent") as parent:
            print("[Parent] Started with 2s timeout")

            # Create child that will be auto-cancelled when parent times out
            child = Cancellable(name="child", parent=parent)

            async with child:
                print("[Child] Started, linked to parent")

                for i in range(10):
                    await anyio.sleep(0.5)
                    print(f"[Child] Working... {i + 1}/10")

    except anyio.get_cancelled_exc_class():
        print(f"[Parent] Timed out as expected")
        print(f"[Child] Also cancelled due to parent timeout")

    print("\n✅ Parent-child cancellation successful!")


if __name__ == "__main__":
    anyio.run(main)
    anyio.run(example_cancel_parent_child)
