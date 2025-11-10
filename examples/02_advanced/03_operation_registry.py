#!/usr/bin/env python3
"""
Operation registry example.
"""

import asyncio
import time

from hother.cancelable import Cancelable, OperationRegistry


async def main() -> None:
    """Run the example."""

    # Example: Using the operation registry

    registry = OperationRegistry.get_instance()
    await registry.clear_all()

    print("  Demonstrating registry with real-time monitoring\n")

    start_time = time.time()

    # Monitor operations in real-time
    async def monitor_operations() -> None:
        """Continuously monitor and display operation status."""
        last_count = -1

        while True:
            await asyncio.sleep(0.5)

            ops = await registry.list_operations()
            elapsed = time.time() - start_time

            # Only print if operation count changed or periodically
            if len(ops) != last_count:
                print(f"  [{elapsed:.1f}s] Active operations: {len(ops)}")
                for op in ops:
                    status = op.status.value
                    duration = (time.time() - op.start_time.timestamp()) if op.start_time else 0
                    print(f"    - {op.name}: {status} (running {duration:.1f}s)")

                if len(ops) > 0:
                    print()

                last_count = len(ops)

                # Stop monitoring when no operations remain
                if len(ops) == 0:
                    break

    # This pattern allows "soft cancelation" without exceptions
    async def monitored_task(task_id: int, duration: float) -> None:
        """Task with timeout-based cancellation using asyncio.timeout()."""
        cancel = Cancelable(name=f"monitored_task_{task_id}", register_globally=True)

        # Use timeout for soft cancelation
        try:
            async with asyncio.timeout(duration):
                async with cancel:
                    for i in range(10):  # Long running task
                        await cancel.report_progress(f"Task {task_id}: step {i + 1}")
                        await asyncio.sleep(0.5)
        except TimeoutError:
            print(f"  Task {task_id}: Timed out")
            return

        print(f"  Task {task_id}: Completed")

    # Run tasks with concurrent monitoring
    async with asyncio.TaskGroup() as tg:
        # Start monitoring task
        tg.create_task(monitor_operations())

        # Start worker tasks with different timeouts
        tg.create_task(monitored_task(1, 5.5))  # Will complete
        tg.create_task(monitored_task(2, 1.5))  # Will timeout
        tg.create_task(monitored_task(3, 10.0))  # Will complete

    # Show final results
    print("\n  Final results:")
    history = await registry.get_history()
    for op in history:
        print(f"    - {op.name}: {op.status.value} (duration: {op.duration_seconds:.1f}s)")

    await registry.clear_all()


if __name__ == "__main__":
    asyncio.run(main())
