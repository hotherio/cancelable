# Custom Cancelation Sources

Build your own cancelation sources for specialized use cases.

## Creating a Custom Source

To create custom cancelation sources, you can extend `CancelationSource`.

### Basic Structure

```python
from hother.cancelable.sources.base import CancelationSource
from hother.cancelable import CancelationReason
import anyio

class CustomSource(CancelationSource):  # (1)!
    """Custom cancelation source."""

    def __init__(self, description: str = "Custom source"):
        super().__init__(description=description)
        # Your custom initialization

    async def monitor(self) -> None:  # (2)!
        """Monitor for cancelation conditions."""
        while not self.is_cancelled:
            if await self.should_cancel():
                await self.trigger_cancelation(
                    reason=CancelationReason.CONDITION,
                    message="Custom condition met"
                )
                break
            await anyio.sleep(self.check_interval)

    async def should_cancel(self) -> bool:  # (3)!
        """Implement your cancelation logic."""
        # Your custom logic here
        return False
```

1. Extend `CancelationSource` to create custom sources
2. The `monitor()` method runs in background to check for cancelation conditions
3. Implement `should_cancel()` with your cancelation logic - return `True` to cancel

### File Watcher Example

```python
from pathlib import Path

class FileWatcherSource(CancelationSource):
    """Cancel when a file appears."""

    def __init__(self, filepath: Path, check_interval: float = 1.0):
        super().__init__(description=f"File watcher: {filepath}")
        self.filepath = filepath
        self.check_interval = check_interval

    async def should_cancel(self) -> bool:  # (1)!
        """Check if the stop file exists."""
        return self.filepath.exists()

    async def monitor(self) -> None:
        """Monitor for file appearance."""
        while not self.is_cancelled:
            if await self.should_cancel():
                await self.trigger_cancelation(
                    reason=CancelationReason.CONDITION,
                    message=f"File {self.filepath} appeared"
                )
                break
            await anyio.sleep(self.check_interval)

# Usage
stop_file = Path("/tmp/stop_processing")
async with Cancelable(
    sources=[FileWatcherSource(stop_file)],
    name="file_processor"
) as cancel:
    await process_files()
```

1. Simple cancelation logic - return `True` when file exists

### HTTP Endpoint Source

```python
import httpx

class HTTPCheckSource(CancelationSource):
    """Cancel when HTTP endpoint returns specific status."""

    def __init__(self, url: str, check_interval: float = 5.0):
        super().__init__(description=f"HTTP check: {url}")
        self.url = url
        self.check_interval = check_interval
        self.client = None

    async def should_cancel(self) -> bool:  # (1)!
        """Check if service is unavailable."""
        try:
            response = await self.client.get(self.url)
            return response.status_code == 503
        except httpx.RequestError:
            return False  # Don't cancel on network errors

    async def monitor(self) -> None:
        """Monitor HTTP endpoint for service availability."""
        async with httpx.AsyncClient() as client:
            self.client = client
            while not self.is_cancelled:
                if await self.should_cancel():
                    await self.trigger_cancelation(
                        reason=CancelationReason.CONDITION,
                        message="Service unavailable"
                    )
                    break
                await anyio.sleep(self.check_interval)
```

1. Wrap checks in try-except and handle errors gracefully - don't accidentally trigger cancelation on errors

## Best Practices

### Keep Monitoring Logic Lightweight

```python
# ✅ Good - simple check
async def should_cancel(self) -> bool:
    return self.filepath.exists()

# ❌ Bad - expensive operation in monitor loop
async def should_cancel(self) -> bool:
    data = await fetch_large_dataset()  # Slow!
    return process_complex_logic(data)
```

### Use Appropriate Check Intervals

```python
# ✅ Good - reasonable intervals
FileWatcherSource(filepath, check_interval=1.0)     # File checks: 1s
HTTPCheckSource(url, check_interval=5.0)            # HTTP checks: 5s
DatabaseCheckSource(query, check_interval=10.0)     # DB checks: 10s

# ❌ Bad - too frequent
FileWatcherSource(filepath, check_interval=0.01)    # 100 checks/second!
```

## Built-in Advanced Sources

### ResourceConditionSource

Pre-built source for monitoring system resources (requires `psutil`):

```python
from hother.cancelable.sources.condition import ResourceConditionSource

# Cancel if memory usage exceeds 90%
memory_source = ResourceConditionSource(
    memory_percent_threshold=90.0,
    check_interval=5.0
)

# Cancel if CPU usage exceeds 95% for 10 seconds
cpu_source = ResourceConditionSource(
    cpu_percent_threshold=95.0,
    check_interval=1.0,
    sustained_seconds=10.0  # Must be sustained for 10s
)

# Cancel if disk usage exceeds 95%
disk_source = ResourceConditionSource(
    disk_percent_threshold=95.0,
    disk_path="/data",
    check_interval=10.0
)

async with Cancelable(
    sources=[memory_source, cpu_source, disk_source],
    name="resource_monitored"
) as cancel:
    await intensive_operation()
```

**Parameters**:
- `memory_percent_threshold` - Memory usage percentage (0-100)
- `cpu_percent_threshold` - CPU usage percentage (0-100)
- `disk_percent_threshold` - Disk usage percentage (0-100)
- `disk_path` - Path to monitor for disk usage
- `sustained_seconds` - Threshold must be sustained for this duration
- `check_interval` - How often to check (seconds)

**Use cases**:
- Production workload protection
- Resource-intensive operations
- Multi-tenant systems

**Note**: Requires `psutil` package (`pip install psutil`)
