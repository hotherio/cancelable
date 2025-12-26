#!/usr/bin/env python3
"""
Condition-based cancelation example.

This example demonstrates how to use custom conditions for cancelation,
including file system monitoring, database state changes, and custom predicates.
"""

import asyncio
import time
from pathlib import Path

from hother.cancelable import Cancelable


async def main():
    """Run all condition cancelation examples."""

    # Example 1: File-based condition for cancelation

    print("\n=== Example 1: File-based condition ===\n")

    # Create a condition that monitors for a stop file
    stop_file = Path("/tmp/stop_signal.txt")

    def check_stop_file():
        """Check if stop file exists."""
        return stop_file.exists()

    # Clean up any existing stop file
    if stop_file.exists():
        stop_file.unlink()

    # Background task to create stop file after delay (simulates external trigger)
    async def create_stop_file_after_delay():
        """Create stop file after a delay to demonstrate condition checking."""
        await asyncio.sleep(2.0)
        stop_file.touch()
        print("  → Stop file created automatically")

    # Run file watcher with automatic file creation
    async with asyncio.TaskGroup() as tg:
        tg.create_task(create_stop_file_after_delay())

        async with Cancelable.with_condition(check_stop_file, condition_name="file_exists", name="file_watcher") as cancel:
            print(f"  Started file watcher: {cancel.context.id}")
            print("  Waiting for stop file to appear...")

            try:
                for i in range(100):
                    await cancel.report_progress(f"Watching for stop file... ({i + 1}/100)")
                    await asyncio.sleep(0.5)

                    # Check condition manually (normally this would be automatic)
                    if check_stop_file():
                        print("  Stop file detected!")
                        break

                print("  File watching completed")

            except asyncio.CancelledError:
                print("  File watcher was cancelled")

    # Cleanup
    if stop_file.exists():
        stop_file.unlink()

    # Example 2: Database state monitoring

    print("\n=== Example 2: Database state monitoring ===\n")

    # Simulate database state
    db_state = {"status": "processing", "records_processed": 0}

    def check_db_complete():
        """Check if database operation is complete."""
        return db_state["status"] == "complete"

    def check_db_error():
        """Check if database has errors."""
        return bool(db_state.get("error", False))

    # Create condition-based cancelables
    complete_cancel = Cancelable.with_condition(check_db_complete, condition_name="db_complete", name="complete_monitor")
    error_cancel = Cancelable.with_condition(check_db_error, condition_name="db_error", name="error_monitor")

    # Combine conditions (cancel if either complete or error)
    combined_cancel = complete_cancel.combine(error_cancel)

    async with combined_cancel as cancel:
        print(f"  Started database monitor: {cancel.context.id}")

        try:
            for i in range(20):
                await cancel.report_progress(f"Processing database records... ({i + 1}/20)")
                await asyncio.sleep(0.3)

                # Simulate database progress
                db_state["records_processed"] = i + 1

                # Simulate completion at step 15
                if i == 14:
                    db_state["status"] = "complete"
                    print("  Database operation completed!")
                    break

                # Simulate occasional errors
                if i == 10 and (i % 3) == 0:
                    db_state["error"] = True
                    print("  Database error detected!")
                    break

            print("  Database monitoring completed")

        except asyncio.CancelledError:
            print("  Database monitor was cancelled")

    # Example 3: Custom predicates with complex logic

    print("\n=== Example 3: System health monitoring ===\n")

    # Complex state for monitoring
    system_state = {"cpu_usage": 0.0, "memory_usage": 0.0, "active_connections": 0, "error_count": 0}

    def check_system_health():
        """Complex health check predicate."""
        return (
            system_state["cpu_usage"] > 15.0
            or system_state["memory_usage"] > 25.0
            or system_state["active_connections"] > 1000
            or system_state["error_count"] > 5
        )

    def check_quiet_period():
        """Check if system is in a quiet period."""
        return system_state["active_connections"] < 10 and system_state["cpu_usage"] < 20.0

    # Create condition-based cancelables
    health_cancel = Cancelable.with_condition(check_system_health, condition_name="system_health", name="health_monitor")
    quiet_cancel = Cancelable.with_condition(check_quiet_period, condition_name="quiet_period", name="quiet_monitor")

    # Cancel if system becomes unhealthy OR enters quiet period
    combined_cancel = health_cancel.combine(quiet_cancel)

    async with combined_cancel as cancel:
        print(f"  Started system monitor: {cancel.context.id}")

        try:
            for i in range(30):
                # Simulate system metrics
                system_state["cpu_usage"] = 50.0 + (i * 1.5)  # Gradually increasing
                system_state["memory_usage"] = 40.0 + (i * 0.8)
                system_state["active_connections"] = max(0, 50 - i)  # Gradually decreasing
                system_state["error_count"] = i // 10  # Errors every 10 iterations

                await cancel.report_progress(
                    f"System metrics - CPU: {system_state['cpu_usage']:.1f}%, "
                    f"Mem: {system_state['memory_usage']:.1f}%, "
                    f"Conn: {system_state['active_connections']}, "
                    f"Errors: {system_state['error_count']}"
                )

                await asyncio.sleep(0.2)

                # Check conditions
                if check_system_health():
                    print("  System health threshold exceeded!")
                    break
                if check_quiet_period():
                    print("  System entered quiet period!")
                    break

            print("  System monitoring completed")

        except asyncio.CancelledError:
            print("  System monitor was cancelled")

    # Example 4: Timeout with condition-based cancelation

    print("\n=== Example 4: Condition with timeout ===\n")

    # State for monitoring
    progress_state = {"items_processed": 0, "target_reached": False}

    def check_target_reached():
        """Check if processing target is reached."""
        return bool(progress_state["target_reached"])

    # Create sources
    condition_cancel = Cancelable.with_condition(check_target_reached, condition_name="target_check", name="target_monitor")
    timeout_cancel = Cancelable.with_timeout(5.0, name="processing_timeout")

    # Combine condition and timeout
    combined_cancel = condition_cancel.combine(timeout_cancel)

    async with combined_cancel as cancel:
        print(f"  Started conditional timeout operation: {cancel.context.id}")
        print("  Will cancel when target reached OR 5 seconds elapse")

        start_time = time.time()
        try:
            for i in range(50):
                elapsed = time.time() - start_time
                await cancel.report_progress(f"Processing item {i + 1}/50 (elapsed: {elapsed:.1f}s)")
                await asyncio.sleep(0.1)

                progress_state["items_processed"] = i + 1

                # Simulate reaching target at random point
                if i == 25:  # Reach target at item 26
                    progress_state["target_reached"] = True
                    print("  Processing target reached!")
                    break

            print("  Conditional timeout operation completed")

        except asyncio.CancelledError:
            elapsed = time.time() - start_time
            print(f"  Operation cancelled after {elapsed:.1f} seconds")


if __name__ == "__main__":
    print("Condition Cancelation Examples")
    print("==============================")
    print()
    print("This example demonstrates various condition-based cancelation patterns:")
    print("- File system monitoring")
    print("- Database state changes")
    print("- Custom health checks")
    print("- Combined timeout and condition logic")
    print()
    print("Run with: python examples/02_advanced/07_condition_cancelation.py")
    print()

    asyncio.run(main())
