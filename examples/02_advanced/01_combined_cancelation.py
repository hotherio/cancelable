#!/usr/bin/env python3
"""
Combined cancelation sources example.
"""

# --8<-- [start:imports]
import asyncio
import signal

from hother.cancelable import Cancelable, CancelationToken

# --8<-- [end:imports]

SLEEP_DURATION = 0.5


# --8<-- [start:main]
async def main():
    """Run the example."""

    # --8<-- [start:example]
    # Example: Multiple cancelation sources combined

    # Create multiple cancelation sources
    token = CancelationToken()
    print(f"Created manual token: {token.id}")

    # Create individual cancelables with logging
    timeout_cancellable = Cancelable.with_timeout(10.0)
    print(f"Created timeout cancelable: {timeout_cancellable.context.id} with token {timeout_cancellable.token.id}")

    token_cancellable = Cancelable.with_token(token)
    print(f"Created token cancelable: {token_cancellable.context.id} with token {token_cancellable.token.id}")

    signal_cancellable = Cancelable.with_signal(signal.SIGINT)
    print(f"Created signal cancelable: {signal_cancellable.context.id} with token {signal_cancellable.token.id}")

    # Combine them step by step with logging
    print("=== COMBINING STEP 1: timeout + token ===")
    first_combine = timeout_cancellable.combine(token_cancellable)
    print(f"First combine result: {first_combine.context.id} with token {first_combine.token.id}")

    print("=== COMBINING STEP 2: (timeout+token) + signal ===")
    final_cancellable = first_combine.combine(signal_cancellable)
    print(f"Final combine result: {final_cancellable.context.id} with token {final_cancellable.token.id}")

    print(f"Final combined cancelable: {final_cancellable.context.id}")
    print(f"Final combined cancelable token: {final_cancellable.token.id}")

    final_cancellable.on_cancel(
        lambda ctx: print(
            f"  Cancelled: {ctx.cancel_reason.value if ctx.cancel_reason else 'unknown'} - {ctx.cancel_message or 'no message'}"
        )
    )

    print("  Press Ctrl+C to cancel, or wait for timeout/manual cancel...")
    try:
        async with final_cancellable:
            # Simulate work
            for i in range(20):
                await asyncio.sleep(SLEEP_DURATION)
                print(f"  Working... {i + 1}/20")

                # Manual cancel after 3 seconds
                if i == 6 * SLEEP_DURATION:
                    print("  Triggering manual cancelation...")
                    print(f"About to cancel token: {token.id}")
                    await token.cancel(message="Demonstration cancel")
                    print("Token cancel call completed")
    except asyncio.CancelledError:
        print("  Operation was cancelled")
        print(f"  Reason: {final_cancellable.context.cancel_reason.value if final_cancellable.context.cancel_reason else 'unknown'}")
        print(f"  Message: {final_cancellable.context.cancel_message or 'no message'}")
    # --8<-- [end:example]


# --8<-- [end:main]


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
