#!/usr/bin/env python3
"""
Manual token-based cancelation example.
"""

# --8<-- [start:imports]
import anyio

from hother.cancelable import Cancelable, CancelationToken

# --8<-- [end:imports]


# --8<-- [start:main]
async def main() -> None:
    # --8<-- [start:example]
    # Example: Manual cancelation with token

    # Create a cancelation token
    token = CancelationToken()

    async def background_task() -> None:
        """Simulate a long-running task."""
        try:
            async with Cancelable.with_token(token, name="background_task") as cancel:
                cancel.on_progress(lambda op_id, msg, meta: print(f"  Progress: {msg}"))
                for i in range(10):
                    await cancel.report_progress(f"Step {i + 1}/10")
                    await anyio.sleep(0.5)
        except anyio.get_cancelled_exc_class():
            print("  Background task was cancelled!")

    # Run task and cancel after 2 seconds
    try:
        async with anyio.create_task_group() as tg:
            # Start background task
            tg.start_soon(background_task)

            # Cancel after 2 seconds
            await anyio.sleep(2.0)
            print("Cancelling task...")
            await token.cancel(message="User requested cancelation")
    except* anyio.get_cancelled_exc_class():
        # Handle the cancelation from task group
        print("  Task group cancelled due to operation cancelation")
    # --8<-- [end:example]


# --8<-- [end:main]


if __name__ == "__main__":
    anyio.run(main)
