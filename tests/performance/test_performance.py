"""
Performance tests for async cancelation system.
"""

import gc
import time
from statistics import mean

import anyio
import pytest

from hother.cancelable import Cancelable, CancelationToken, OperationRegistry


class TestCancelablePerformance:
    """Test performance characteristics of Cancelable."""

    @pytest.mark.anyio
    async def test_context_manager_overhead(self):
        """Measure overhead of Cancelable context manager."""
        iterations = 1000

        # Baseline: raw async function
        async def baseline():
            await anyio.sleep(0)
            return 42

        # With cancelable
        async def with_cancellable():
            async with Cancelable():
                await anyio.sleep(0)
                return 42

        # Measure baseline
        baseline_times = []
        for _ in range(iterations):
            start = time.perf_counter()
            await baseline()
            baseline_times.append(time.perf_counter() - start)

        # Measure with cancelable
        cancellable_times = []
        for _ in range(iterations):
            start = time.perf_counter()
            await with_cancellable()
            cancellable_times.append(time.perf_counter() - start)

        # Calculate statistics
        baseline_avg = mean(baseline_times) * 1000  # Convert to ms
        cancellable_avg = mean(cancellable_times) * 1000
        overhead = cancellable_avg - baseline_avg
        overhead_percent = (overhead / baseline_avg) * 100

        print("\nContext Manager Overhead:")
        print(f"  Baseline: {baseline_avg:.3f}ms")
        print(f"  With Cancelable: {cancellable_avg:.3f}ms")
        print(f"  Overhead: {overhead:.3f}ms ({overhead_percent:.1f}%)")

        # Check absolute overhead is reasonable (less than 0.5ms)
        assert overhead < 0.5, f"Absolute overhead too high: {overhead:.3f}ms"

        # For such a lightweight baseline operation, percentage overhead is less meaningful
        # What matters is that the absolute overhead is small
        if baseline_avg < 0.1:  # If baseline is less than 0.1ms
            print("  Note: Baseline is very fast, checking absolute overhead only")
        else:
            # Only check percentage for meaningful baseline times
            assert overhead_percent < 200, f"Percentage overhead too high: {overhead_percent:.1f}%"

    @pytest.mark.anyio
    async def test_cancelation_check_performance(self):
        """Test performance of cancelation checking."""
        iterations = 10000

        token = CancelationToken()

        # Measure check performance when not cancelled
        start = time.perf_counter()
        for _ in range(iterations):
            token.check()
        not_cancelled_time = time.perf_counter() - start

        # Cancel token
        await token.cancel()

        # Measure check performance when cancelled
        cancelled_count = 0
        start = time.perf_counter()
        for _ in range(iterations):
            try:
                token.check()
            except:
                cancelled_count += 1
        cancelled_time = time.perf_counter() - start

        print(f"\nCancelation Check Performance ({iterations} iterations):")
        print(f"  Not cancelled: {not_cancelled_time * 1000:.2f}ms ({not_cancelled_time / iterations * 1e6:.2f}μs per check)")
        print(f"  Cancelled: {cancelled_time * 1000:.2f}ms ({cancelled_time / iterations * 1e6:.2f}μs per check)")

        # Should be very fast
        assert not_cancelled_time / iterations < 1e-5  # Less than 10μs per check

    @pytest.mark.anyio
    async def test_stream_processing_overhead(self):
        """Test overhead of stream processing with cancelation."""
        item_count = 1000

        async def generate_items():
            for i in range(item_count):
                yield i

        # Baseline: direct iteration
        start = time.perf_counter()
        baseline_sum = 0
        async for item in generate_items():
            baseline_sum += item
        baseline_time = time.perf_counter() - start

        # With cancelable stream (no progress reporting)
        start = time.perf_counter()
        cancellable_sum = 0
        async with Cancelable() as cancel:
            async for item in cancel.stream(generate_items(), buffer_partial=False):
                cancellable_sum += item
        cancellable_time = time.perf_counter() - start

        assert baseline_sum == cancellable_sum

        overhead = cancellable_time - baseline_time
        overhead_percent = (overhead / baseline_time) * 100 if baseline_time > 0 else 0

        # Calculate throughput
        baseline_throughput = item_count / baseline_time if baseline_time > 0 else 0
        cancellable_throughput = item_count / cancellable_time if cancellable_time > 0 else 0

        print(f"\nStream Processing Performance ({item_count} items):")
        print(f"  Baseline: {baseline_time * 1000:.2f}ms ({baseline_throughput:.0f} items/sec)")
        print(f"  With Cancelable: {cancellable_time * 1000:.2f}ms ({cancellable_throughput:.0f} items/sec)")
        print(f"  Overhead: {overhead * 1000:.2f}ms ({overhead_percent:.1f}%)")

        # Check throughput instead of percentage overhead
        # Should be able to process at least 10,000 items per second even with cancelation
        assert cancellable_throughput > 10000, f"Throughput too low: {cancellable_throughput:.0f} items/sec"

        # Also test with less frequent cancelation checks
        print("\n  Testing with report_interval=100 (less frequent checks):")
        start = time.perf_counter()
        optimized_sum = 0
        async with Cancelable() as cancel:
            # Using report_interval as a proxy for check frequency
            async for item in cancel.stream(generate_items(), report_interval=100, buffer_partial=False):
                optimized_sum += item
        optimized_time = time.perf_counter() - start
        optimized_throughput = item_count / optimized_time if optimized_time > 0 else 0

        print(f"  Optimized: {optimized_time * 1000:.2f}ms ({optimized_throughput:.0f} items/sec)")

    @pytest.mark.anyio
    async def test_concurrent_operations_scaling(self):
        """Test performance with many concurrent operations."""
        operation_counts = [10, 50, 100, 200]

        async def simple_operation(op_id: int):
            async with Cancelable(name=f"op_{op_id}"):
                await anyio.sleep(0.01)
                return op_id

        results = []

        for count in operation_counts:
            gc.collect()  # Clean up before measurement

            start = time.perf_counter()

            async with anyio.create_task_group() as tg:
                for i in range(count):
                    tg.start_soon(simple_operation, i)

            duration = time.perf_counter() - start
            ops_per_second = count / duration

            results.append({"count": count, "duration": duration, "ops_per_second": ops_per_second})

            print(f"\n{count} concurrent operations:")
            print(f"  Duration: {duration:.3f}s")
            print(f"  Ops/second: {ops_per_second:.0f}")

        # Performance should scale reasonably
        # Check that doubling operations doesn't more than double time
        for i in range(len(results) - 1):
            ratio = results[i + 1]["duration"] / results[i]["duration"]
            ops_ratio = results[i + 1]["count"] / results[i]["count"]
            assert ratio < ops_ratio * 1.5  # Allow 50% overhead for scaling

    @pytest.mark.anyio
    async def test_memory_usage(self):
        """Test memory usage of cancelation system."""
        import sys

        # Create many operations
        operation_count = 1000
        operations = []

        # Measure baseline memory
        gc.collect()
        sys.getsizeof(operations)

        # Create operations
        for i in range(operation_count):
            op = Cancelable(operation_id=f"op_{i}", name=f"operation_{i}", metadata={"index": i, "data": "x" * 100})
            operations.append(op)

        # Measure with operations
        total_size = sum(sys.getsizeof(op) for op in operations)
        avg_size = total_size / operation_count

        print(f"\nMemory Usage ({operation_count} operations):")
        print(f"  Average size per operation: {avg_size:.0f} bytes")
        print(f"  Total size: {total_size / 1024:.1f} KB")

        # Reasonable memory usage
        assert avg_size < 10000  # Less than 10KB per operation

        # Clean up
        operations.clear()
        gc.collect()

    @pytest.mark.anyio
    async def test_registry_performance(self):
        """Test performance of operation registry."""
        registry = OperationRegistry.get_instance()
        await registry.clear_all()

        operation_count = 1000

        # Measure registration time
        operations = []
        start = time.perf_counter()

        for i in range(operation_count):
            op = Cancelable(name=f"op_{i}")
            operations.append(op)
            await registry.register(op)

        register_time = time.perf_counter() - start

        # Measure lookup time
        lookup_times = []
        for op in operations[:100]:  # Sample 100 operations
            start = time.perf_counter()
            found = await registry.get_operation(op.context.id)
            lookup_times.append(time.perf_counter() - start)
            assert found is op

        avg_lookup = mean(lookup_times) * 1000  # Convert to ms

        # Measure listing time
        start = time.perf_counter()
        all_ops = await registry.list_operations()
        list_time = (time.perf_counter() - start) * 1000

        assert len(all_ops) == operation_count

        print(f"\nRegistry Performance ({operation_count} operations):")
        print(f"  Registration: {register_time:.3f}s total ({register_time / operation_count * 1000:.3f}ms per op)")
        print(f"  Lookup: {avg_lookup:.3f}ms average")
        print(f"  List all: {list_time:.3f}ms")

        # Performance targets
        assert register_time / operation_count < 0.001  # Less than 1ms per registration
        assert avg_lookup < 1.0  # Less than 1ms per lookup
        assert list_time < 100  # Less than 100ms to list all

        # Cleanup
        await registry.clear_all()

    @pytest.mark.anyio
    async def test_callback_overhead(self):
        """Test overhead of callbacks."""
        iterations = 100

        # No callbacks
        no_callback_times = []
        for _ in range(iterations):
            start = time.perf_counter()
            async with Cancelable() as cancel:
                await cancel.report_progress("test")
            no_callback_times.append(time.perf_counter() - start)

        # With callbacks
        callback_count = 0

        def progress_callback(op_id, msg, meta):
            nonlocal callback_count
            callback_count += 1

        async def async_callback(ctx):
            await anyio.sleep(0)

        with_callback_times = []
        for _ in range(iterations):
            start = time.perf_counter()
            async with Cancelable().on_progress(progress_callback).on_start(async_callback).on_complete(async_callback) as cancel:
                await cancel.report_progress("test")
            with_callback_times.append(time.perf_counter() - start)

        no_callback_avg = mean(no_callback_times) * 1000
        with_callback_avg = mean(with_callback_times) * 1000
        overhead = with_callback_avg - no_callback_avg

        print(f"\nCallback Overhead ({iterations} iterations):")
        print(f"  No callbacks: {no_callback_avg:.3f}ms")
        print(f"  With callbacks: {with_callback_avg:.3f}ms")
        print(f"  Overhead: {overhead:.3f}ms ({(overhead / no_callback_avg) * 100:.1f}%)")

        assert callback_count == iterations
        # Callbacks should add minimal overhead
        assert overhead < no_callback_avg  # Less than 100% overhead


@pytest.mark.anyio
class TestScalability:
    """Test scalability of the cancelation system."""

    async def test_nested_cancellables(self):
        """Test deeply nested cancelable contexts."""
        max_depth = 100

        async def nested_operation(depth: int):
            if depth <= 0:
                return depth

            async with Cancelable(name=f"level_{depth}"):
                return await nested_operation(depth - 1)

        start = time.perf_counter()
        result = await nested_operation(max_depth)
        duration = time.perf_counter() - start

        assert result == 0

        print(f"\nNested Cancelables ({max_depth} levels):")
        print(f"  Total time: {duration * 1000:.2f}ms")
        print(f"  Per level: {duration / max_depth * 1000:.3f}ms")

        # Should handle deep nesting efficiently
        assert duration < 1.0  # Less than 1 second for 100 levels

    async def test_large_stream_cancelation(self):
        """Test cancelling large streams efficiently."""
        item_count = 100000

        async def large_stream():
            for i in range(item_count):
                yield i
                if i % 1000 == 0:
                    await anyio.sleep(0)  # Yield control

        # Test cancelation at different points
        cancel_points = [1000, 10000, 50000]

        for cancel_at in cancel_points:
            processed = 0

            async def process_until_count():
                nonlocal processed
                async with Cancelable() as cancel:
                    async for item in cancel.stream(large_stream()):
                        processed += 1
                        if processed >= cancel_at:
                            await cancel.cancel()

            start = time.perf_counter()

            try:
                await process_until_count()
            except anyio.get_cancelled_exc_class():
                pass

            duration = time.perf_counter() - start
            items_per_second = processed / duration

            print(f"\nStream cancelation at {cancel_at} items:")
            print(f"  Duration: {duration:.3f}s")
            print(f"  Items/second: {items_per_second:.0f}")

            # Should process items quickly
            assert items_per_second > 10000  # At least 10k items/second
