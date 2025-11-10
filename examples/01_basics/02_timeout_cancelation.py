#!/usr/bin/env python3
"""
Timeout-based cancelation example.
"""

# --8<-- [start:imports]
import anyio

from hother.cancelable import Cancelable

# --8<-- [end:imports]


# --8<-- [start:main]
async def main() -> None:
    # --8<-- [start:example]
    # Example: Timeout-based cancelation
    cancel = None
    try:
        async with Cancelable.with_timeout(2.0, name="timeout_example") as cancel:
            cancel.on_progress(lambda op_id, msg, meta: print(f"  Progress: {msg}"))

            await cancel.report_progress("Starting operation")

            # This will timeout
            await anyio.sleep(5.0)

            await cancel.report_progress("This won't be reached")

    except anyio.get_cancelled_exc_class():
        if cancel:
            print(f"  Operation timed out after {(cancel.context.duration.total_seconds() if cancel.context.duration else 0.0):.2f}s")
            print(f"  Final status: {cancel.context.status.value}")
            print(
                f"  Cancel reason: {cancel.context.cancel_reason.value if cancel.context.cancel_reason else 'unknown'}"
            )
    # --8<-- [end:example]


# --8<-- [end:main]


if __name__ == "__main__":
    anyio.run(main)
