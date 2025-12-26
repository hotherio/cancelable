#!/usr/bin/env python3
"""
Resource monitoring with ResourceConditionSource and psutil.

This example demonstrates how to use ResourceConditionSource to monitor
system resources (memory, CPU, disk) and automatically cancel operations
when resource thresholds are exceeded.

IMPORTANT: This example requires psutil to be installed:
    pip install psutil
    # or
    uv add psutil

Use cases:
- Data processing that should stop if memory gets too high
- CPU-intensive tasks that should pause if system is overloaded
- Disk operations that should stop if disk space is running low
- Long-running operations with resource constraints
"""

import asyncio

import anyio

from hother.cancelable import Cancelable
from hother.cancelable.sources.condition import ResourceConditionSource

# Check if psutil is available
try:
    import psutil

    _psutil = psutil
    _has_psutil = True
except ImportError:
    _psutil = None
    _has_psutil = False
    print("psutil not installed - examples will use mock data")


def get_current_resources():
    """Get current system resource usage."""
    if _has_psutil and _psutil is not None:
        return {
            "memory": _psutil.virtual_memory().percent,
            "cpu": _psutil.cpu_percent(interval=0.1),
            "disk": _psutil.disk_usage("/").percent,
        }
    # Mock data if psutil not available
    return {"memory": 50.0, "cpu": 40.0, "disk": 60.0}


async def main():
    """Run all resource monitoring examples."""

    if not _has_psutil:
        print("⚠ WARNING: psutil is not installed!")
        print("   Install with: pip install psutil")
        print("   Examples will run with mock data\n")
    else:
        print("✓ psutil is installed - using real system metrics\n")

    print("These examples demonstrate automatic cancelation when")
    print("system resources exceed specified thresholds.")
    print()

    # Show current system resources
    resources = get_current_resources()
    print("Current System Resources:")
    print(f"  Memory: {resources['memory']:.1f}%")
    print(f"  CPU:    {resources['cpu']:.1f}%")
    print(f"  Disk:   {resources['disk']:.1f}%")
    print()

    try:
        # Example 1: Memory-intensive data processing with monitoring

        # Create resource monitor for memory
        # This will check memory every 1 second and cancel if > 80%
        cancelable = Cancelable(name="data_processing").add_source(
            ResourceConditionSource(
                memory_threshold=80.0,  # Cancel if memory > 80%
                check_interval=1.0,
                name="memory_monitor",
            )
        )

        print("Starting data processing with memory monitoring (threshold: 80%)")
        resources = get_current_resources()
        print(f"Current memory usage: {resources['memory']:.1f}%\n")

        try:
            async with cancelable:
                # Simulate processing large batches of data
                total_items = 100
                batch_size = 10

                for batch_num in range(total_items // batch_size):
                    await cancelable.report_progress(f"Processing batch {batch_num + 1}/{total_items // batch_size}")

                    # Simulate work
                    await anyio.sleep(0.5)

                    # Check and report memory
                    resources = get_current_resources()
                    if batch_num % 2 == 0:  # Report every other batch
                        print(f"  Batch {batch_num + 1}: Memory at {resources['memory']:.1f}%")

                print("\n✓ Data processing completed successfully!")

        except asyncio.CancelledError:
            resources = get_current_resources()
            print("\n⚠ Processing cancelled due to high memory usage!")
            print(f"  Memory was at {resources['memory']:.1f}% (threshold: 80%)")
            print("  This prevents system instability from excessive memory use")

        await anyio.sleep(1)  # Brief pause between examples

        # Example 2: CPU-intensive computation with monitoring

        # Monitor CPU usage - cancel if > 90%
        cancelable = Cancelable(name="computation").add_source(
            ResourceConditionSource(
                cpu_threshold=90.0,  # Cancel if CPU > 90%
                check_interval=0.5,
                name="cpu_monitor",
            )
        )

        print("Starting computation with CPU monitoring (threshold: 90%)")
        resources = get_current_resources()
        print(f"Current CPU usage: {resources['cpu']:.1f}%\n")

        try:
            async with cancelable:
                # Simulate CPU-intensive work
                iterations = 50

                for i in range(iterations):
                    await cancelable.report_progress(f"Computing iteration {i + 1}/{iterations}")

                    # Simulate computation
                    await anyio.sleep(0.3)

                    # Check and report CPU
                    resources = get_current_resources()
                    if i % 10 == 0:
                        print(f"  Iteration {i + 1}: CPU at {resources['cpu']:.1f}%")

                print("\n✓ Computation completed successfully!")

        except asyncio.CancelledError:
            resources = get_current_resources()
            print("\n⚠ Computation cancelled due to high CPU usage!")
            print(f"  CPU was at {resources['cpu']:.1f}% (threshold: 90%)")
            print("  This prevents system overload and maintains responsiveness")

        await anyio.sleep(1)

        # Example 3: Disk operations with space monitoring

        # Monitor disk usage - cancel if > 95%
        cancelable = Cancelable(name="file_operations").add_source(
            ResourceConditionSource(
                disk_threshold=95.0,  # Cancel if disk > 95%
                check_interval=1.0,
                name="disk_monitor",
            )
        )

        print("Starting file operations with disk monitoring (threshold: 95%)")
        resources = get_current_resources()
        print(f"Current disk usage: {resources['disk']:.1f}%\n")

        try:
            async with cancelable:
                # Simulate writing files
                num_files = 20

                for file_num in range(num_files):
                    await cancelable.report_progress(f"Writing file {file_num + 1}/{num_files}")

                    # Simulate file write
                    await anyio.sleep(0.4)

                    # Check and report disk
                    resources = get_current_resources()
                    if file_num % 5 == 0:
                        print(f"  File {file_num + 1}: Disk at {resources['disk']:.1f}%")

                print("\n✓ File operations completed successfully!")

        except asyncio.CancelledError:
            resources = get_current_resources()
            print("\n⚠ File operations cancelled due to low disk space!")
            print(f"  Disk was at {resources['disk']:.1f}% (threshold: 95%)")
            print("  This prevents filling up the disk completely")

        await anyio.sleep(1)

        # Example 4: Monitor all resources simultaneously

        # Monitor all three resources with different thresholds
        cancelable = Cancelable(name="multi_resource_operation").add_source(
            ResourceConditionSource(
                memory_threshold=80.0,  # 80% memory
                cpu_threshold=90.0,  # 90% CPU
                disk_threshold=95.0,  # 95% disk
                check_interval=1.0,
                name="combined_monitor",
            )
        )

        print("Starting operation with combined resource monitoring")
        resources = get_current_resources()
        print("Current resources:")
        print(f"  Memory: {resources['memory']:.1f}% (threshold: 80%)")
        print(f"  CPU:    {resources['cpu']:.1f}% (threshold: 90%)")
        print(f"  Disk:   {resources['disk']:.1f}% (threshold: 95%)")
        print()

        try:
            async with cancelable:
                # Simulate complex operation
                total_steps = 30

                for step in range(total_steps):
                    await cancelable.report_progress(f"Processing step {step + 1}/{total_steps}")

                    # Simulate work
                    await anyio.sleep(0.5)

                    # Check and report resources periodically
                    if step % 10 == 0:
                        resources = get_current_resources()
                        print(f"  Step {step + 1}:")
                        print(f"    Memory: {resources['memory']:.1f}%")
                        print(f"    CPU:    {resources['cpu']:.1f}%")
                        print(f"    Disk:   {resources['disk']:.1f}%")

                print("\n✓ Operation completed successfully!")

        except asyncio.CancelledError:
            resources = get_current_resources()
            print("\n⚠ Operation cancelled due to resource constraint!")
            print("  Current resources:")
            print(f"    Memory: {resources['memory']:.1f}% (threshold: 80%)")
            print(f"    CPU:    {resources['cpu']:.1f}% (threshold: 90%)")
            print(f"    Disk:   {resources['disk']:.1f}% (threshold: 95%)")

        await anyio.sleep(1)

        # Example 5: Real-world use case - Data export with resource monitoring

        # Conservative thresholds for production use
        cancelable = Cancelable(name="data_export").add_source(
            ResourceConditionSource(
                memory_threshold=75.0,  # More conservative 75% memory
                cpu_threshold=85.0,  # 85% CPU
                disk_threshold=90.0,  # 90% disk
                check_interval=2.0,  # Check every 2 seconds
                name="export_monitor",
            )
        )

        print("Starting data export with conservative resource monitoring")
        print("Thresholds: Memory 75%, CPU 85%, Disk 90%")
        resources = get_current_resources()
        print(f"Current: Memory {resources['memory']:.1f}%, CPU {resources['cpu']:.1f}%, Disk {resources['disk']:.1f}%\n")

        try:
            async with cancelable:
                # Simulate multi-stage export process
                stages = [
                    ("Extracting data from database", 5),
                    ("Transforming data", 5),
                    ("Formatting output", 3),
                    ("Writing to disk", 7),
                    ("Compressing files", 5),
                ]

                for stage_name, num_chunks in stages:
                    print(f"\n{stage_name}:")

                    for chunk in range(num_chunks):
                        await cancelable.report_progress(f"{stage_name} - chunk {chunk + 1}/{num_chunks}")

                        # Simulate chunk processing
                        await anyio.sleep(0.6)

                        # Show progress
                        print(f"  Chunk {chunk + 1}/{num_chunks} processed")

                    # Report resources after each stage
                    resources = get_current_resources()
                    print(
                        f"  Resources: Mem {resources['memory']:.1f}%, "
                        f"CPU {resources['cpu']:.1f}%, Disk {resources['disk']:.1f}%"
                    )

                print("\n✓ Data export completed successfully!")
                print("  Exported data safely while monitoring resource usage")

        except asyncio.CancelledError:
            resources = get_current_resources()
            print("\n⚠ Data export cancelled due to resource constraints!")
            print("  Resources when cancelled:")
            print(f"    Memory: {resources['memory']:.1f}% (threshold: 75%)")
            print(f"    CPU:    {resources['cpu']:.1f}% (threshold: 85%)")
            print(f"    Disk:   {resources['disk']:.1f}% (threshold: 90%)")
            print("\n  Partial export can be resumed later when resources are available")

    except KeyboardInterrupt:
        print("\n\nExamples interrupted by user")


if __name__ == "__main__":
    print("\nResource Monitoring Examples")
    print("============================")
    print()
    print("This example demonstrates ResourceConditionSource with psutil")
    print("for monitoring system resources during long-running operations.")
    print()
    print("Key Features:")
    print("  • Automatic cancelation when resources exceed thresholds")
    print("  • Monitor memory, CPU, and/or disk usage")
    print("  • Prevent system instability from resource exhaustion")
    print("  • Graceful handling when resources become constrained")
    print()

    if not _has_psutil:
        print("⚠ psutil is not installed - examples will use mock data")
        print("  Install psutil to monitor real system resources:")
        print("    pip install psutil")
        print()

    print("Press Ctrl+C to stop\n")

    try:
        anyio.run(main)
    except KeyboardInterrupt:
        print("\nStopped by user")
