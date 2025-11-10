"""Performance tests for scalability."""

import gc
import time

import anyio
import pytest

from hother.cancelable import Cancelable, OperationRegistry


class TestScalability:
    """Test scalability of the cancelation system."""

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

    @pytest.mark.anyio
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

    @pytest.mark.anyio
    async def test_registry_performance(self):
        """Test performance of operation registry at scale."""
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

        from statistics import mean

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
    async def test_memory_usage(self):
        """Test memory usage at scale."""
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
