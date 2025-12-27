"""
AND Logic (All-Of) Combining Example

Demonstrates using AllOfSource to require ALL conditions before cancelling.

Use case: Batch processing that requires:
1. Minimum processing time (60 seconds)
2. Minimum number of items processed (100 items)

Only stops when BOTH conditions are met.
"""

import time

import anyio

from hother.cancelable import Cancelable
from hother.cancelable.sources.composite import AllOfSource
from hother.cancelable.sources.condition import ConditionSource
from hother.cancelable.sources.timeout import TimeoutSource


async def batch_processor_with_requirements():
    """
    Batch processor that enforces quality requirements.

    Ensures:
    - At least 60 seconds of processing time
    - At least 100 items processed

    Both requirements must be met before stopping.
    """
    items_processed = 0
    start_time = time.time()

    print("=== Batch Processor with AND Logic ===\n")
    print("Requirements:")
    print("  - Minimum 60 seconds processing time")
    print("  - Minimum 100 items processed")
    print("  - BOTH must be satisfied to stop\n")

    # Create individual sources
    min_time_source = TimeoutSource(timeout=60.0)
    min_items_source = ConditionSource(
        condition=lambda: items_processed >= 100,
        check_interval=0.5,
    )

    # Combine with AND logic - both must trigger
    all_of = AllOfSource([min_time_source, min_items_source], name="batch_requirements")

    # Create cancelable and add the all-of source
    cancelable = Cancelable(name="batch_job")
    cancelable.add_source(all_of)

    try:
        async with cancelable:
            print("Starting batch processing...")
            print("Press Ctrl+C to interrupt (demonstrates graceful handling)\n")

            while True:
                # Simulate processing
                await anyio.sleep(0.5)
                items_processed += 1

                elapsed = time.time() - start_time

                # Show progress every 10 items
                if items_processed % 10 == 0:
                    print(
                        f"Progress: {items_processed:3d} items | "
                        f"{elapsed:5.1f}s elapsed | "
                        f"Time req: {'✅' if elapsed >= 60 else '⏳'} | "
                        f"Items req: {'✅' if items_processed >= 100 else '⏳'}"
                    )

    except anyio.get_cancelled_exc_class():
        elapsed = time.time() - start_time
        print("\n✅ Batch processing completed!")
        print(f"Final: {items_processed} items processed in {elapsed:.1f}s")
        print(f"Requirements met: Time={elapsed >= 60}, Items={items_processed >= 100}")


async def demonstration_fast_items_slow_time():
    """
    Demonstrate AND logic where items complete quickly but time requirement not met.

    Fast processing: 100 items in ~10 seconds
    Time requirement: 30 seconds minimum
    Result: Continues until 30 seconds pass
    """
    items_processed = 0
    start_time = time.time()

    print("\n=== Demo: Fast Items, Slow Time ===")
    print("Processing 100 items quickly (~10s)")
    print("But minimum time is 30 seconds")
    print("Should continue for full 30 seconds\n")

    min_time = TimeoutSource(timeout=30.0)
    min_items = ConditionSource(condition=lambda: items_processed >= 100, check_interval=0.5)

    all_of = AllOfSource([min_time, min_items])
    cancelable = Cancelable(name="fast_items")
    cancelable.add_source(all_of)

    try:
        async with cancelable:
            while True:
                await anyio.sleep(0.1)  # Fast processing
                items_processed += 1

                if items_processed % 25 == 0:
                    elapsed = time.time() - start_time
                    print(
                        f"{items_processed:3d} items | {elapsed:5.1f}s | "
                        f"Items: {'✓' if items_processed >= 100 else '...'} | "
                        f"Time: {'✓' if elapsed >= 30 else '...'}"
                    )

    except anyio.get_cancelled_exc_class():
        elapsed = time.time() - start_time
        print(f"\n✅ Completed: {items_processed} items in {elapsed:.1f}s " f"(waited for time requirement)")


async def demonstration_slow_items_fast_time():
    """
    Demonstrate AND logic where time passes quickly but items not met.

    Slow processing: ~20 items in 10 seconds
    Item requirement: 50 items minimum
    Result: Continues until 50 items processed
    """
    items_processed = 0
    start_time = time.time()

    print("\n=== Demo: Slow Items, Fast Time ===")
    print("Time requirement: 10 seconds (passes quickly)")
    print("Item requirement: 50 items (takes longer)")
    print("Should continue until 50 items processed\n")

    min_time = TimeoutSource(timeout=10.0)
    min_items = ConditionSource(condition=lambda: items_processed >= 50, check_interval=0.5)

    all_of = AllOfSource([min_time, min_items])
    cancelable = Cancelable(name="slow_items")
    cancelable.add_source(all_of)

    try:
        async with cancelable:
            while True:
                await anyio.sleep(0.5)  # Slow processing
                items_processed += 1

                if items_processed % 10 == 0:
                    elapsed = time.time() - start_time
                    print(
                        f"{items_processed:3d} items | {elapsed:5.1f}s | "
                        f"Time: {'✓' if elapsed >= 10 else '...'} | "
                        f"Items: {'✓' if items_processed >= 50 else '...'}"
                    )

    except anyio.get_cancelled_exc_class():
        elapsed = time.time() - start_time
        print(f"\n✅ Completed: {items_processed} items in {elapsed:.1f}s " f"(waited for item requirement)")


async def main():
    """Run all demonstrations."""
    print("\n" + "=" * 70)
    print("AllOfSource (AND Logic) Demonstration")
    print("=" * 70 + "\n")

    # Demo 1: Fast items, must wait for time
    await demonstration_fast_items_slow_time()

    await anyio.sleep(1)

    # Demo 2: Fast time, must wait for items
    await demonstration_slow_items_fast_time()

    await anyio.sleep(1)

    # Main batch processor example
    # Uncomment to run (takes 60+ seconds):
    # await batch_processor_with_requirements()

    print("\n" + "=" * 70)
    print("Demonstrations complete!")
    print("\nKey takeaway: AND logic ensures ALL conditions are met,")
    print("not just the first one to trigger.")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    anyio.run(main)
