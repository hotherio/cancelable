#!/usr/bin/env python3
"""
Critical edge case demonstrations for the hother.cancelable library.

This file demonstrates the REAL edge cases that need fixing in the cancellation system.
These are not theoretical issues but actual bugs that can cause problems in production.
"""

import asyncio
import gc
import threading
from concurrent.futures import ThreadPoolExecutor

import anyio

from hother.cancelable import Cancellable
from hother.cancelable.utils.logging import configure_logging, get_logger

# Configure logging
configure_logging(log_level="WARNING")  # Reduce noise for edge case demos
logger = get_logger(__name__)


async def edge_case_context_variable_thread_safety():
    """
    CRITICAL BUG: Context variable thread safety issues.

    Problem: Context variables don't propagate correctly across thread boundaries
    in complex async applications. This breaks operation tracking and debugging
    in multi-threaded environments.

    Impact: Operations started in the main thread become invisible to background
    threads, making debugging and monitoring impossible.
    """
    print("\n🚨 CRITICAL BUG: Context Variable Thread Safety")
    print("=" * 50)

    from hother.cancelable.core.cancellable import _current_operation

    results = []

    def check_context_in_thread(iteration: int):
        """Check context variable from a thread."""
        try:
            # Try to get current operation from thread
            current = _current_operation.get()
            results.append((iteration, current is not None, threading.current_thread().name))
            return f"Thread {iteration}: context={'present' if current else 'missing'}"
        except Exception as e:
            results.append((iteration, f"error: {e}", threading.current_thread().name))
            return f"Thread {iteration}: error={e}"

    # Test context variable propagation using the new run_in_thread method
    async with Cancellable(name="context_test") as cancel:
        print(f"Main thread context: {_current_operation.get() is not None}")

        # Run multiple thread checks using the new context-safe method
        thread_results = await asyncio.gather(*[
            cancel.run_in_thread(check_context_in_thread, i) for i in range(5)
        ])

        print("Thread execution results:")
        for result in thread_results:
            print(f"  {result}")

    # Analyze results
    context_propagated = sum(1 for _, propagated, _ in results if propagated)
    context_failed = sum(1 for _, propagated, _ in results if not propagated)

    print(f"\nContext propagated to threads: {context_propagated}")
    print(f"Context failed in threads: {context_failed}")

    for iteration, result, thread_name in results:
        print(f"  Thread {iteration} ({thread_name}): {result}")

    if context_failed > 0:
        print("\n❌ BUG CONFIRMED: Context variables don't propagate to threads")
        print("   This breaks operation tracking in multi-threaded applications!")
        return False
    else:
        print("\n✅ Context variables working correctly - FIXED!")
        return True


async def edge_case_circular_references():
    """
    CRITICAL BUG: Circular references in parent-child relationships.

    Problem: Parent-child cancellable relationships create circular references that
    prevent garbage collection, causing memory leaks in long-running applications.

    Impact: Memory usage grows indefinitely in applications with nested operations,
    eventually leading to out-of-memory crashes.
    """
    print("\n🚨 CRITICAL BUG: Circular References in Parent-Child Relationships")
    print("=" * 65)

    # Track object counts
    initial_objects = len(gc.get_objects())

    # Create a deep hierarchy of cancellables
    root = Cancellable(name="root")
    current = root

    # Create a deep chain: root -> child1 -> child2 -> ... -> child100
    for i in range(100):
        child = Cancellable(name=f"child_{i}", parent=current)
        current = child

    # Delete the root reference
    del root
    del current

    # Force garbage collection
    collected = gc.collect()

    # Check if objects were properly collected
    final_objects = len(gc.get_objects())
    object_growth = final_objects - initial_objects

    print(f"Objects before creating hierarchy: {initial_objects}")
    print(f"Objects after cleanup: {final_objects}")
    print(f"Objects collected by GC: {collected}")
    print(f"Object growth: {object_growth}")

    # In a well-behaved system, most objects should be collected
    if object_growth > 50:  # Allow some growth for internal objects
        print("\n❌ BUG CONFIRMED: Circular references prevent garbage collection")
        print(f"   {object_growth} objects retained, causing memory leaks!")
        return False
    else:
        print("\n✅ No significant circular reference issues detected")
        return True


async def main():
    """Run critical edge case demonstrations."""
    print("🚨 Hother.Cancelable CRITICAL BUG Demonstrations")
    print("=" * 55)
    print("These demonstrate REAL BUGS that MUST be fixed before production use.")
    print("Each test shows an actual problem that can cause crashes or data loss.\n")

    critical_bugs = [
        edge_case_context_variable_thread_safety,
        edge_case_circular_references,
    ]

    results = []
    for bug_test in critical_bugs:
        try:
            result = await bug_test()
            results.append(result)
        except Exception as e:
            print(f"❌ Bug test failed with exception: {e}")
            results.append(False)

    print("\n" + "=" * 55)
    print("CRITICAL BUG REPORT:")
    # Results are False when bugs are confirmed (tests that find bugs return False)
    bugs_confirmed = sum(1 for r in results if r is False)
    total_tests = len(results)
    print(f"Bug tests run: {total_tests}")
    print(f"Bugs confirmed: {bugs_confirmed}")
    print(f"Bugs resolved: {total_tests - bugs_confirmed}")

    if bugs_confirmed > 0:
        print("\n🚨 CRITICAL BUGS DETECTED!")
        print("These bugs MUST be fixed before production deployment:")
        print("1. Context variables don't propagate to threads (breaks debugging)")
        print("2. Circular references cause memory leaks (crashes long-running apps)")
        print("\nThese are not theoretical issues - they can cause real problems!")
    else:
        print("\n✅ All critical bugs resolved!")
        print("The cancellation system is ready for production use.")

    return results


if __name__ == "__main__":
    anyio.run(main)