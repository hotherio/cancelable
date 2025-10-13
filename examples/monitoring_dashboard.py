#!/usr/bin/env python3
"""
Real-time monitoring dashboard for async operations.
"""

import signal
from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Any, Dict, List

import anyio

from hother.cancelable import Cancellable, OperationRegistry, OperationStatus, cancellable
from hother.cancelable.utils.logging import configure_logging, get_logger

# Configure logging
configure_logging(log_level="INFO")
logger = get_logger(__name__)


class OperationMonitor:
    """Monitor and analyze operation patterns."""

    def __init__(self, history_size: int = 1000):
        self.history_size = history_size
        self.operation_history: deque = deque(maxlen=history_size)
        self.error_counts: Dict[str, int] = defaultdict(int)
        self.duration_stats: Dict[str, List[float]] = defaultdict(list)
        self.cancellation_reasons: Dict[str, int] = defaultdict(int)

    def record_operation(self, operation):
        """Record operation for analysis."""
        self.operation_history.append(
            {
                "id": operation.id,
                "name": operation.name,
                "status": operation.status.value,
                "duration": operation.duration_seconds,
                "timestamp": datetime.utcnow(),
            }
        )

        # Track errors
        if operation.status == OperationStatus.FAILED:
            self.error_counts[operation.name or "unnamed"] += 1

        # Track durations
        if operation.duration_seconds and operation.name:
            self.duration_stats[operation.name].append(operation.duration_seconds)
            # Keep only recent durations
            if len(self.duration_stats[operation.name]) > 100:
                self.duration_stats[operation.name] = self.duration_stats[operation.name][-100:]

        # Track cancellation reasons
        if operation.cancel_reason:
            self.cancellation_reasons[operation.cancel_reason.value] += 1

    def get_statistics(self) -> Dict[str, Any]:
        """Get current statistics."""
        # Calculate success rate
        recent_ops = list(self.operation_history)[-100:]  # Last 100 operations
        if recent_ops:
            success_count = sum(1 for op in recent_ops if op["status"] == "completed")
            success_rate = (success_count / len(recent_ops)) * 100
        else:
            success_rate = 0

        # Calculate average durations
        avg_durations = {}
        for name, durations in self.duration_stats.items():
            if durations:
                avg_durations[name] = sum(durations) / len(durations)

        return {
            "total_operations": len(self.operation_history),
            "success_rate": round(success_rate, 2),
            "error_counts": dict(self.error_counts),
            "average_durations": avg_durations,
            "cancellation_reasons": dict(self.cancellation_reasons),
        }


class DashboardServer:
    """Simple dashboard server for monitoring operations."""

    def __init__(self, monitor: OperationMonitor):
        self.monitor = monitor
        self.registry = OperationRegistry.get_instance()
        self.running = True
        self._update_interval = 1.0

    async def update_loop(self, cancellable: Cancellable):
        """Main update loop for dashboard."""
        while self.running:
            try:
                # Get current operations
                operations = await self.registry.list_operations()

                # Clear screen (simple approach)
                print("\033[2J\033[H")  # ANSI escape codes

                # Display header
                print("=" * 80)
                print("🚀 Async Operations Dashboard".center(80))
                print("=" * 80)
                print(f"Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
                print()

                # Active operations
                print("📊 Active Operations:")
                print("-" * 80)

                if operations:
                    # Group by status
                    by_status = defaultdict(list)
                    for op in operations:
                        by_status[op.status.value].append(op)

                    for status, ops in sorted(by_status.items()):
                        print(f"\n{status.upper()} ({len(ops)}):")
                        for op in ops[:5]:  # Show max 5 per status
                            duration = f"{op.duration_seconds:.1f}s" if op.duration_seconds else "0.0s"
                            print(f"  • [{op.id[:8]}] {op.name or 'unnamed':<30} {duration:>10}")

                        if len(ops) > 5:
                            print(f"  ... and {len(ops) - 5} more")
                else:
                    print("  No active operations")

                # Statistics
                stats = self.monitor.get_statistics()
                print("\n📈 Statistics:")
                print("-" * 80)
                print(f"Total operations: {stats['total_operations']}")
                print(f"Success rate (last 100): {stats['success_rate']}%")

                if stats["error_counts"]:
                    print("\n❌ Error counts:")
                    for name, count in sorted(stats["error_counts"].items(), key=lambda x: x[1], reverse=True)[:5]:
                        print(f"  • {name}: {count}")

                if stats["average_durations"]:
                    print("\n⏱️  Average durations:")
                    for name, avg in sorted(stats["average_durations"].items(), key=lambda x: x[1], reverse=True)[:5]:
                        print(f"  • {name}: {avg:.2f}s")

                if stats["cancellation_reasons"]:
                    print("\n🛑 Cancellation reasons:")
                    for reason, count in sorted(stats["cancellation_reasons"].items(), key=lambda x: x[1], reverse=True):
                        print(f"  • {reason}: {count}")

                # Recent history
                recent = list(self.monitor.operation_history)[-10:]
                if recent:
                    print("\n📜 Recent operations:")
                    print("-" * 80)
                    for op in reversed(recent):
                        status_icon = {
                            "completed": "✅",
                            "failed": "❌",
                            "cancelled": "🛑",
                            "timeout": "⏱️",
                        }.get(op["status"], "❓")

                        duration = f"{op['duration']:.1f}s" if op["duration"] else "N/A"
                        print(f"{status_icon} [{op['id'][:8]}] {op['name'] or 'unnamed':<30} {duration:>10}")

                print("\n" + "=" * 80)
                print("Press Ctrl+C to exit | Operations update every second")

                # Check for cancellation
                await cancellable._token.check_async()

                # Wait before next update
                await anyio.sleep(self._update_interval)

            except anyio.get_cancelled_exc_class():
                raise
            except Exception as e:
                logger.error(f"Dashboard update error: {e}", exc_info=True)
                await anyio.sleep(self._update_interval)

    async def run(self):
        """Run the dashboard."""
        async with Cancellable.with_signal(signal.SIGINT, name="dashboard") as cancel:
            cancel.on_cancel(lambda ctx: print("\n👋 Dashboard shutting down..."))

            try:
                await self.update_loop(cancel)
            except anyio.get_cancelled_exc_class():
                self.running = False


# Simulated workloads for demonstration
@cancellable(register_globally=True)
async def simulated_api_call(
    endpoint: str,
    duration: float,
    fail_rate: float = 0.1,
    cancellable: Cancellable = None,
):
    """Simulate an API call."""
    import random

    await cancellable.report_progress(f"Calling {endpoint}")

    # Simulate work
    steps = int(duration * 10)
    for i in range(steps):
        await anyio.sleep(0.1)

        # Random failure
        if random.random() < fail_rate:
            raise Exception(f"API call to {endpoint} failed")

    await cancellable.report_progress(f"Completed {endpoint}")
    return {"endpoint": endpoint, "status": "success"}


@cancellable(register_globally=True)
async def simulated_data_processing(
    dataset_id: str,
    record_count: int,
    cancellable: Cancellable = None,
):
    """Simulate data processing."""
    batch_size = 100
    processed = 0

    while processed < record_count:
        batch = min(batch_size, record_count - processed)

        # Simulate processing
        await anyio.sleep(0.2)
        processed += batch

        await cancellable.report_progress(f"Processed {processed}/{record_count} records", {"progress_percent": (processed / record_count) * 100})

    return {"dataset_id": dataset_id, "records_processed": processed}


@cancellable(register_globally=True, timeout=5.0)
async def simulated_file_download(
    file_id: str,
    size_mb: float,
    cancellable: Cancellable = None,
):
    """Simulate file download."""
    downloaded = 0
    chunk_size = 0.5  # MB

    while downloaded < size_mb:
        chunk = min(chunk_size, size_mb - downloaded)

        # Simulate download
        await anyio.sleep(0.3)
        downloaded += chunk

        progress = (downloaded / size_mb) * 100
        await cancellable.report_progress(f"Downloading: {progress:.1f}%", {"downloaded_mb": downloaded, "total_mb": size_mb})

    return {"file_id": file_id, "size_mb": size_mb}


async def workload_generator(monitor: OperationMonitor):
    """Generate random workloads for demonstration."""
    import random

    workloads = [
        lambda: simulated_api_call(
            random.choice(["/users", "/orders", "/products", "/analytics"]),
            random.uniform(0.5, 3.0),
            fail_rate=0.15,
        ),
        lambda: simulated_data_processing(
            f"dataset_{random.randint(100, 999)}",
            random.randint(500, 5000),
        ),
        lambda: simulated_file_download(
            f"file_{random.randint(1000, 9999)}",
            random.uniform(1.0, 10.0),
        ),
    ]

    # Start monitoring completed operations
    registry = OperationRegistry.get_instance()

    async def monitor_completed():
        """Monitor and record completed operations."""
        last_check = datetime.utcnow()

        while True:
            await anyio.sleep(2.0)

            # Get operations completed since last check
            history = await registry.get_history(since=last_check)
            for op in history:
                monitor.record_operation(op)

            last_check = datetime.utcnow()

            # Cleanup old operations
            await registry.cleanup_completed(older_than=timedelta(minutes=5))

    async def run_workload_with_error_handling(workload_func):
        """Run a workload and handle any errors."""
        try:
            await workload_func()
        except Exception as e:
            # Log but don't crash - this is expected for simulated failures
            logger.debug(f"Simulated workload failed (expected): {e}")

    # Start workload generation
    async with anyio.create_task_group() as tg:
        # Start monitoring task
        tg.start_soon(monitor_completed)

        # Generate workloads
        while True:
            # Random delay between operations
            await anyio.sleep(random.uniform(0.5, 2.0))

            # Start random workload with error handling
            workload = random.choice(workloads)
            tg.start_soon(run_workload_with_error_handling, workload)

            # Limit concurrent operations
            active = await registry.list_operations()
            if len(active) > 10:
                await anyio.sleep(2.0)


async def example_dashboard():
    """Run the monitoring dashboard example."""
    print("Starting monitoring dashboard...")
    print("Generating simulated workloads...")
    print("Dashboard will appear in 3 seconds...")

    await anyio.sleep(3)

    # Create monitor and dashboard
    monitor = OperationMonitor()
    dashboard = DashboardServer(monitor)

    # Run dashboard and workload generator
    async with anyio.create_task_group() as tg:
        # Start workload generator
        tg.start_soon(workload_generator, monitor)

        # Run dashboard
        await dashboard.run()


async def example_api_monitoring():
    """Example: Monitor API endpoint performance."""
    print("\n=== API Endpoint Monitoring ===")

    # Simulate API endpoints with different characteristics
    endpoints = [
        {"path": "/api/users", "avg_time": 0.5, "error_rate": 0.05},
        {"path": "/api/orders", "avg_time": 1.0, "error_rate": 0.1},
        {"path": "/api/products", "avg_time": 0.3, "error_rate": 0.02},
        {"path": "/api/analytics", "avg_time": 2.0, "error_rate": 0.15},
    ]

    # Track metrics
    metrics = {
        "request_count": defaultdict(int),
        "error_count": defaultdict(int),
        "response_times": defaultdict(list),
        "concurrent_requests": defaultdict(int),
    }

    @cancellable(register_globally=True)
    async def simulate_request(
        endpoint: dict,
        request_id: int,
        cancellable: Cancellable = None,
    ):
        """Simulate API request with monitoring."""
        path = endpoint["path"]
        metrics["concurrent_requests"][path] += 1

        try:
            # Simulate variable response time
            import random

            duration = random.gauss(endpoint["avg_time"], endpoint["avg_time"] * 0.3)
            duration = max(0.1, duration)  # Minimum 100ms

            await anyio.sleep(duration)

            # Random errors
            if random.random() < endpoint["error_rate"]:
                raise Exception(f"Request {request_id} failed")

            # Record success
            metrics["request_count"][path] += 1
            metrics["response_times"][path].append(duration)

            # Keep only recent response times
            if len(metrics["response_times"][path]) > 100:
                metrics["response_times"][path] = metrics["response_times"][path][-100:]

            return {"path": path, "duration": duration, "status": "success"}

        except Exception:
            metrics["error_count"][path] += 1
            raise
        finally:
            metrics["concurrent_requests"][path] -= 1

    # Generate load
    print("Generating API load for 20 seconds...")
    print("Monitoring endpoint performance...\n")

    async with Cancellable.with_timeout(20.0, name="api_monitoring") as cancel:
        request_id = 0

        async def generate_load():
            nonlocal request_id
            while True:
                # Pick random endpoint
                import random

                endpoint = random.choice(endpoints)

                # Start request
                request_id += 1
                async with anyio.create_task_group() as tg:
                    tg.start_soon(simulate_request, endpoint, request_id)

                # Variable rate
                await anyio.sleep(random.uniform(0.05, 0.2))

        async def display_metrics():
            """Display metrics periodically."""
            while True:
                await anyio.sleep(2.0)

                print("\033[2J\033[H")  # Clear screen
                print("API Endpoint Metrics")
                print("=" * 60)

                for endpoint in endpoints:
                    path = endpoint["path"]
                    total = metrics["request_count"][path]
                    errors = metrics["error_count"][path]
                    concurrent = metrics["concurrent_requests"][path]

                    if total > 0:
                        error_rate = (errors / (total + errors)) * 100
                    else:
                        error_rate = 0

                    response_times = metrics["response_times"][path]
                    if response_times:
                        avg_time = sum(response_times) / len(response_times)
                        p95_time = sorted(response_times)[int(len(response_times) * 0.95)]
                    else:
                        avg_time = 0
                        p95_time = 0

                    print(f"\n{path}:")
                    print(f"  Requests: {total:,} | Errors: {errors} ({error_rate:.1f}%)")
                    print(f"  Concurrent: {concurrent}")
                    print(f"  Avg time: {avg_time:.3f}s | P95: {p95_time:.3f}s")

                # Check cancellation
                await cancel._token.check_async()

        # Run both tasks
        async with anyio.create_task_group() as tg:
            tg.start_soon(generate_load)
            tg.start_soon(display_metrics)


async def example_resource_monitoring():
    """Example: Monitor system resources during operations."""
    print("\n=== Resource Monitoring ===")

    try:
        import psutil
    except ImportError:
        print("psutil not available, skipping resource monitoring example")
        return

    class ResourceMonitor:
        """Monitor system resources."""

        def __init__(self):
            self.cpu_history = deque(maxlen=60)
            self.memory_history = deque(maxlen=60)
            self.operation_count = 0

        def record_snapshot(self):
            """Record current resource usage."""
            self.cpu_history.append(psutil.cpu_percent(interval=0.1))
            self.memory_history.append(psutil.virtual_memory().percent)

        def get_summary(self):
            """Get resource summary."""
            if not self.cpu_history:
                return {}

            return {
                "cpu_current": self.cpu_history[-1],
                "cpu_avg": sum(self.cpu_history) / len(self.cpu_history),
                "cpu_max": max(self.cpu_history),
                "memory_current": self.memory_history[-1],
                "memory_avg": sum(self.memory_history) / len(self.memory_history),
                "memory_max": max(self.memory_history),
            }

    monitor = ResourceMonitor()

    # CPU-intensive workload
    @cancellable(register_globally=True)
    async def cpu_intensive_task(task_id: int, cancellable: Cancellable = None):
        """Simulate CPU-intensive work."""
        import hashlib

        data = f"task_{task_id}".encode()
        iterations = 50000

        for i in range(iterations):
            if i % 10000 == 0:
                await cancellable.report_progress(f"Task {task_id}: {i}/{iterations} iterations")
                # Allow cancellation
                await anyio.sleep(0)

            # CPU work
            hashlib.pbkdf2_hmac("sha256", data, b"salt", 100)

        return task_id

    print("Starting resource monitoring with CPU-intensive tasks...")
    print("Monitoring for 30 seconds...\n")

    async with Cancellable.with_timeout(30.0, name="resource_monitoring"):

        async def run_workloads():
            """Run CPU-intensive workloads."""
            task_id = 0

            while True:
                # Start new task
                task_id += 1
                monitor.operation_count += 1

                async with anyio.create_task_group() as tg:
                    tg.start_soon(cpu_intensive_task, task_id)

                # Adjust rate based on CPU usage
                summary = monitor.get_summary()
                if summary.get("cpu_avg", 0) > 80:
                    await anyio.sleep(2.0)  # Slow down
                else:
                    await anyio.sleep(0.5)  # Normal rate

        async def monitor_resources():
            """Monitor and display resources."""
            while True:
                monitor.record_snapshot()

                # Display every 2 seconds
                if len(monitor.cpu_history) % 2 == 0:
                    summary = monitor.get_summary()

                    print("\033[2J\033[H")  # Clear screen
                    print("Resource Monitoring")
                    print("=" * 50)
                    print(f"Active operations: {monitor.operation_count}")
                    print()
                    print(f"CPU:    Current: {summary['cpu_current']:.1f}%")
                    print(f"        Average: {summary['cpu_avg']:.1f}%")
                    print(f"        Maximum: {summary['cpu_max']:.1f}%")
                    print()
                    print(f"Memory: Current: {summary['memory_current']:.1f}%")
                    print(f"        Average: {summary['memory_avg']:.1f}%")
                    print(f"        Maximum: {summary['memory_max']:.1f}%")

                    # Show CPU graph
                    print("\nCPU History (last 60 seconds):")
                    print(create_simple_graph(list(monitor.cpu_history), height=10))

                await anyio.sleep(1.0)

        # Run both tasks
        async with anyio.create_task_group() as tg:
            tg.start_soon(run_workloads)
            tg.start_soon(monitor_resources)


def create_simple_graph(values: List[float], height: int = 10, width: int = 50) -> str:
    """Create a simple ASCII graph."""
    if not values:
        return "No data"

    # Normalize values
    max_val = max(values) or 1
    normalized = [int((v / max_val) * height) for v in values]

    # Downsample if needed
    if len(normalized) > width:
        step = len(normalized) / width
        normalized = [normalized[int(i * step)] for i in range(width)]

    # Create graph
    lines = []
    for h in range(height, -1, -1):
        line = ""
        for v in normalized:
            if v >= h:
                line += "█"
            else:
                line += " "

        label = f"{(h / height) * max_val:5.1f}% |"
        lines.append(label + line)

    return "\n".join(lines)


async def main():
    """Run monitoring examples."""
    print("Async Cancellation - Monitoring Dashboard Examples")
    print("=================================================")

    examples = [
        ("Interactive Dashboard", example_dashboard),
        ("API Endpoint Monitoring", example_api_monitoring),
        ("Resource Monitoring", example_resource_monitoring),
    ]

    for name, example in examples:
        print(f"\n{'=' * 60}")
        print(f"Example: {name}")
        print(f"{'=' * 60}")

        try:
            await example()
        except KeyboardInterrupt:
            print("\nExample interrupted by user")
        except Exception as e:
            logger.error(f"Example failed: {e}", exc_info=True)

        print("\nPress Enter to continue to next example...")
        input()


if __name__ == "__main__":
    anyio.run(main)
