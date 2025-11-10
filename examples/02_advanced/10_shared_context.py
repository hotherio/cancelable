"""
Advanced Example: Shared Cancelable Context with @with_cancelable

This example demonstrates how to use the @with_cancelable decorator to share
a single Cancelable instance across multiple functions, providing cleaner
function signatures and better separation of concerns.

Key concepts:
1. Using @with_cancelable to wrap functions with existing Cancelable instance
2. Accessing context via current_operation() without injection
3. Sharing cancelation state across multiple operations
4. Clean function signatures without cancel parameters
"""

from typing import Any

import anyio
from hother.cancelable import Cancelable, with_cancelable, current_operation


# Example 1: Shared context with current_operation()
# ====================================================

# Create a shared cancelable context for the entire data pipeline
pipeline_cancel = Cancelable.with_timeout(30.0, name="data_pipeline")


@with_cancelable(pipeline_cancel)
async def fetch_data(source: str) -> dict[str, Any]:
    """Fetch data from source - clean signature, no cancel parameter."""
    # Access the context via current_operation()
    ctx = current_operation()
    if ctx:
        await ctx.report_progress(f"Fetching data from {source}")

    # Simulate data fetching
    await anyio.sleep(0.5)

    return {"source": source, "records": 1000, "status": "success"}


@with_cancelable(pipeline_cancel)
async def validate_data(data: dict[str, Any]) -> dict[str, Any]:
    """Validate data - clean signature."""
    ctx = current_operation()
    if ctx:
        await ctx.report_progress("Validating data quality")

    # Simulate validation
    await anyio.sleep(0.3)

    data["validated"] = True
    return data


@with_cancelable(pipeline_cancel)
async def transform_data(data: dict[str, Any]) -> dict[str, Any]:
    """Transform data - clean signature."""
    ctx = current_operation()
    if ctx:
        await ctx.report_progress("Transforming data")

    # Simulate transformation
    await anyio.sleep(0.4)

    data["transformed"] = True
    return data


@with_cancelable(pipeline_cancel)
async def save_data(data: dict[str, Any]) -> str:
    """Save data - clean signature."""
    ctx = current_operation()
    if ctx:
        await ctx.report_progress("Saving to database")

    # Simulate saving
    await anyio.sleep(0.2)

    return f"Saved {data['records']} records successfully"


async def run_pipeline():
    """Run the complete data pipeline with shared cancelation."""
    print("\n=== Example 1: Shared Context with current_operation() ===\n")

    # All functions share the pipeline_cancel context
    async with pipeline_cancel:
        try:
            # Clean, sequential pipeline calls
            data = await fetch_data("API")
            data = await validate_data(data)
            data = await transform_data(data)
            result = await save_data(data)

            print(f"✓ Pipeline completed: {result}")

        except anyio.get_cancelled_exc_class():
            print("✗ Pipeline cancelled (timeout)")


# Example 2: Shared context with optional injection
# ==================================================


@with_cancelable(pipeline_cancel, inject=True)
async def fetch_with_injection(source: str, cancelable: Cancelable) -> dict[str, Any]:
    """Fetch data with explicit injection for direct access."""
    # Can access via parameter instead of current_operation()
    await cancelable.report_progress(f"Fetching from {source} (with injection)")

    await anyio.sleep(0.5)
    return {"source": source, "records": 500}


async def run_pipeline_with_injection():
    """Run pipeline with injection enabled."""
    print("\n=== Example 2: Shared Context with Injection ===\n")

    async with pipeline_cancel:
        try:
            data = await fetch_with_injection("Database")
            print(f"✓ Fetched {data['records']} records with injection")

        except anyio.get_cancelled_exc_class():
            print("✗ Pipeline cancelled")


# Example 3: Multiple operations sharing timeout
# ==============================================


async def run_concurrent_tasks():
    """Run multiple concurrent tasks sharing the same cancelation context."""
    print("\n=== Example 3: Concurrent Tasks with Shared Timeout ===\n")

    # Create a shared timeout for all tasks
    shared_cancel = Cancelable.with_timeout(5.0, name="concurrent_tasks")

    @with_cancelable(shared_cancel)
    async def task_a():
        ctx = current_operation()
        if ctx:
            await ctx.report_progress("Task A: Starting")
        await anyio.sleep(1.0)
        if ctx:
            await ctx.report_progress("Task A: Working")
        await anyio.sleep(1.0)
        return "Task A completed"

    @with_cancelable(shared_cancel)
    async def task_b():
        ctx = current_operation()
        if ctx:
            await ctx.report_progress("Task B: Starting")
        await anyio.sleep(0.5)
        if ctx:
            await ctx.report_progress("Task B: Working")
        await anyio.sleep(0.5)
        return "Task B completed"

    @with_cancelable(shared_cancel)
    async def task_c():
        ctx = current_operation()
        if ctx:
            await ctx.report_progress("Task C: Starting")
        await anyio.sleep(1.5)
        if ctx:
            await ctx.report_progress("Task C: Working")
        await anyio.sleep(1.5)
        return "Task C completed"

    # All tasks share the 5-second timeout
    async with shared_cancel:
        try:
            async with anyio.create_task_group() as tg:
                tg.start_soon(task_a)
                tg.start_soon(task_b)
                tg.start_soon(task_c)

            print("✓ All tasks completed successfully")

        except anyio.get_cancelled_exc_class():
            print("✗ Tasks cancelled due to shared timeout")


# Example 4: Workflow with mixed decorator styles
# ===============================================


async def run_mixed_workflow():
    """Demonstrate mixing @with_cancelable with regular Cancelable usage."""
    print("\n=== Example 4: Mixed Decorator Styles ===\n")

    workflow_cancel = Cancelable.with_timeout(10.0, name="mixed_workflow")

    @with_cancelable(workflow_cancel)
    async def step_with_decorator(data: str) -> str:
        ctx = current_operation()
        if ctx:
            await ctx.report_progress("Step 1: Using decorator")
        await anyio.sleep(0.3)
        return f"Processed: {data}"

    async def step_without_decorator(data: str) -> str:
        # Access via current_operation() even without decorator
        ctx = current_operation()
        if ctx:
            await ctx.report_progress("Step 2: Manual context access")
        await anyio.sleep(0.3)
        return f"Transformed: {data}"

    async with workflow_cancel:
        try:
            # Step 1: Uses decorator
            result1 = await step_with_decorator("input_data")
            print(f"  Step 1 result: {result1}")

            # Step 2: Direct call within the context
            result2 = await step_without_decorator(result1)
            print(f"  Step 2 result: {result2}")

            print("✓ Mixed workflow completed")

        except anyio.get_cancelled_exc_class():
            print("✗ Workflow cancelled")


# Example 5: Testing timeout behavior
# ===================================


async def test_timeout_with_shared_context():
    """Test that timeout is properly shared across decorated functions."""
    print("\n=== Example 5: Testing Shared Timeout ===\n")

    # Create a very short timeout
    timeout_cancel = Cancelable.with_timeout(0.5, name="timeout_test")

    @with_cancelable(timeout_cancel)
    async def slow_operation():
        ctx = current_operation()
        if ctx:
            await ctx.report_progress("Starting slow operation")
        # This will timeout
        await anyio.sleep(2.0)
        return "Should not reach here"

    async with timeout_cancel:
        try:
            result = await slow_operation()
            print(f"✓ Result: {result}")
        except anyio.get_cancelled_exc_class():
            print("✗ Operation cancelled due to 0.5s timeout (expected)")
            print(f"  Cancel reason: {timeout_cancel.context.cancel_reason}")


# Main execution
# =============


async def main():
    """Run all examples demonstrating shared Cancelable contexts."""
    print("=" * 70)
    print("Shared Cancelable Context Examples with @with_cancelable")
    print("=" * 70)

    # Run all examples
    await run_pipeline()
    await run_pipeline_with_injection()
    await run_concurrent_tasks()
    await run_mixed_workflow()
    await test_timeout_with_shared_context()

    print("\n" + "=" * 70)
    print("Key Takeaways:")
    print("=" * 70)
    print("1. Use @with_cancelable(cancel) for clean function signatures")
    print("2. Access context via current_operation() when injection=False")
    print("3. Share cancelation state across multiple operations")
    print("4. Timeout/cancellation applies to ALL decorated functions")
    print("5. Mix decorator styles as needed for flexibility")
    print("=" * 70)


if __name__ == "__main__":
    anyio.run(main)
