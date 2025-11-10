# Monitoring Dashboard Examples

Build real-time monitoring and observability.

_Find the complete source in [`examples/05_monitoring/`](https://github.com/hotherio/cancelable/tree/main/examples/05_monitoring)._

## Real-Time Dashboard

Monitor all active cancelable operations.

### Basic Dashboard

```python
from hother.cancelable import OperationRegistry
from rich.console import Console
from rich.table import Table

async def display_dashboard():
    console = Console()
    registry = OperationRegistry.get_instance()

    while True:
        console.clear()

        table = Table(title="Active Operations")
        table.add_column("Operation")
        table.add_column("Status")
        table.add_column("Progress")
        table.add_column("Elapsed")

        for op in registry.get_active_operations():
            table.add_row(
                op.name,
                op.status.value,
                f"{op.progress:.1f}%",
                f"{op.elapsed_time:.1f}s"
            )

        console.print(table)
        await anyio.sleep(1.0)
```

**Run it:**
```bash
python examples/05_monitoring/01_monitoring_dashboard.py
```

## Progress Tracking

Report and visualize operation progress:

```python
async with Cancelable(name="processor") as cancel:
    cancel.on_progress(
        lambda op, msg, meta: update_dashboard(op, meta)
    )

    for i, item in enumerate(items):
        await process_item(item)
        await cancel.report_progress(
            f"Processed {i}/{len(items)}",
            {"progress": (i / len(items)) * 100}
        )
```

## Alert System

Detect and alert on stuck operations:

```python
async def monitor_for_alerts():
    registry = OperationRegistry.get_instance()

    while True:
        for op in registry.get_active_operations():
            if op.elapsed_time > 300:  # 5 minutes
                await send_alert(f"Long-running: {op.name}")

        await anyio.sleep(60)
```

## Metrics Export

Export to Prometheus, Datadog, etc:

```python
def export_metrics():
    registry = OperationRegistry.get_instance()
    active = registry.get_active_operations()

    return {
        "active_operations": len(active),
        "longest_running": max((op.elapsed_time for op in active), default=0)
    }
```

## Use Cases

- Production operation monitoring
- Dashboard visualization
- Alert systems for stuck operations
- Metrics export to observability platforms

## Next Steps

- Learn [Operation Registry](../registry.md) - Registry details
- See [Advanced Usage](../advanced.md) - Progress patterns
- Read [Advanced Patterns](../patterns.md) - Production monitoring
