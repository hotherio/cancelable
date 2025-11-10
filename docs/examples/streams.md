# Stream Processing Examples

Handle async streams with cancelation and backpressure.

_Find the complete source in [`examples/04_streams/`](https://github.com/hotherio/cancelable/tree/main/examples/04_streams)._

## Cancelable Stream Processing

Process async streams with automatic cancelation support.

### Basic Stream Processing

```python
from hother.cancelable import cancelable_stream, Cancelable

async def process_stream():
    async with Cancelable.with_timeout(60.0) as cancel:
        async for item in cancelable_stream(data_stream, cancel):
            await process_item(item)
            # Stream automatically stops on cancelation
```

**Run it:**
```bash
python examples/04_streams/01_stream_processing.py
```

### Features

- **Backpressure Handling** - Buffer management for fast producers
- **Progress Reporting** - Track stream processing progress
- **Chunked Processing** - Process in batches with cancelation
- **Transform & Filter** - Streaming transformations

## Use Cases

- Data pipelines with timeout protection
- ETL operations with progress tracking
- Real-time data processing
- Event stream handling

## Next Steps

- Learn [Basic Patterns](basic.md) - Cancelation fundamentals
- Read [Core Concepts](../streaming.md) - Stream processing details
