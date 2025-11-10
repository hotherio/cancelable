"""Performance tests for measuring overhead."""

import time
from statistics import mean

import anyio
import pytest

from hother.cancelable import Cancelable, CancelationToken


class TestPerformanceOverhead:
    """Test performance overhead of cancelation system."""

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
