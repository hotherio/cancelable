# Cancelable Examples

This directory contains comprehensive examples demonstrating the `hother.cancelable` library's capabilities for async cancelation in Python.

## Directory Structure

```
examples/
├── 01_basics/                    # Basic concepts and usage patterns
│   ├── 01_basic_cancelation.py     # Context managers and basic cancelation
│   ├── 02_timeout_cancelation.py   # Timeout-based cancelation
│   ├── 03_manual_cancelation.py    # Manual token cancelation
│   └── 04_decorated_functions.py    # Using decorators for cancelation
├── 02_advanced/                  # Advanced patterns and techniques
│   ├── 01_combined_cancelation.py     # Combining multiple cancelation sources
│   ├── 02_shielded_operations.py       # Shielding operations from cancelation
│   ├── 03_operation_registry.py        # Global operation registry
│   ├── 04_with_timeout_helper.py       # Timeout helper utilities
│   ├── 05_cancelable_cancel_from_thread.py  # Cross-thread cancelation
│   ├── 06_cancelable_cancel_from_async.py   # Cross-async cancelation
│   ├── 07_condition_cancelation.py    # Custom condition-based cancelation
│   └── 08_signal_handling.py           # Signal-based cancelation
├── 03_integrations/              # Third-party integrations
│   └── 04_fastapi_example.py           # FastAPI integration with request-scoped cancelation
├── 04_streams/                   # Stream processing patterns
│   └── 01_stream_processing.py         # Advanced stream processing with cancelation
├── 05_monitoring/                # Monitoring and observability
│   └── 01_monitoring_dashboard.py      # Real-time operation monitoring dashboard
├── 06_llm/                      # Large Language Model integrations
│   └── 01_llm_streaming.py             # LLM streaming with keyboard and LLM-initiated cancelation
├── backend_validation/           # Internal validation and testing
└── README.md                     # This file
```

## Quick Start

### Running Examples

Each example can be run independently:

```bash
# Basic cancelation concepts
python examples/01_basics/01_basic_cancelation.py

# Advanced patterns
python examples/02_advanced/07_condition_cancelation.py

# FastAPI integration
python examples/03_integrations/04_fastapi_example.py
```

### Learning Path

Follow this progression for the best learning experience:

1. **Start with Basics** (`01_basics/`)
   - Learn context managers, timeouts, and manual cancelation
   - Understand the core `Cancelable` class

2. **Explore Advanced Patterns** (`02_advanced/`)
   - Combine multiple cancelation sources
   - Handle cross-thread and cross-async cancelation
   - Use conditions and signals for sophisticated control

3. **Integrate with Frameworks** (`03_integrations/`)
   - See how cancelable works with FastAPI
   - Learn request-scoped and dependency injection patterns

4. **Process Streams** (`04_streams/`)
   - Handle streaming data with cancelation
   - Learn chunked processing and backpressure

5. **Monitor Operations** (`05_monitoring/`)
   - Build dashboards and observability tools
   - Track operation lifecycle and performance

6. **Integrate LLMs** (`06_llm/`)
   - Handle streaming LLM responses with cancelation
   - Use keyboard input for real-time pause/resume control
   - Implement LLM-initiated pause with special markers
   - Resume conversations from exact position with context preservation

## Example Categories

### Basic Concepts (`01_basics/`)

- **Context Managers**: Using `Cancelable` as an async context manager
- **Timeouts**: Automatic cancelation after time limits
- **Manual Cancelation**: Using `CancelationToken` for explicit control
- **Decorators**: Applying cancelation to functions with decorators

### Advanced Patterns (`02_advanced/`)

- **Composition**: Combining timeouts, signals, and conditions
- **Shielding**: Protecting critical operations from cancelation
- **Registry**: Global operation tracking and management
- **Cross-Context**: Cancelation between threads and async tasks
- **Conditions**: Custom logic-based cancelation triggers
- **Signals**: Unix signal handling for graceful shutdowns

### Framework Integrations (`03_integrations/`)

- **FastAPI**: Request-scoped cancelation with automatic cleanup and client disconnect handling

## Key Concepts Demonstrated

### Cancelation Sources

The library supports multiple cancelation sources that can be combined:

- **Timeouts**: `Cancelable.with_timeout(seconds)`
- **Signals**: `Cancelable.with_signal(SIGINT, SIGTERM)`
- **Conditions**: `Cancelable.with_condition(predicate_function)`
- **Tokens**: `Cancelable.with_token(cancelation_token)`
- **Manual**: `CancelationToken.cancel()`

### Composition Patterns

```python
# Combine multiple sources
timeout_cancel = Cancelable.with_timeout(30.0)
signal_cancel = Cancelable.with_signal(signal.SIGINT)
combined = timeout_cancel.combine(signal_cancel)

async with combined as cancel:
    # Operation cancels on timeout OR signal
    await do_work()
```

### Error Handling

```python
try:
    async with Cancelable.with_timeout(5.0) as cancel:
        await long_running_operation()
except asyncio.CancelledError:
    # Handle cancelation gracefully
    await cleanup_resources()
```

### Progress Reporting

```python
async with Cancelable(name="data_processor") as cancel:
    for item in items:
        await cancel.report_progress(f"Processing {item}")
        await process_item(item)
```

## Testing Examples

Many examples include interactive elements. For full testing:

```bash
# Test signal handling (requires sending signals from another terminal)
python examples/02_advanced/08_signal_handling.py

# Test file monitoring
python examples/02_advanced/07_condition_cancelation.py

# Test FastAPI server
uv add uvicorn fastapi
uvicorn examples.03_integrations.04_fastapi_example:app --host 0.0.0.0 --port 8000
```

## Backend Validation

The `backend_validation/` directory contains internal validation scripts used for testing different async backends (anyio, asyncio) and ensuring compatibility across different scenarios.

## Contributing Examples

When adding new examples:

1. Follow the numbering scheme (`01_`, `02_`, etc.)
2. Include comprehensive docstrings
3. Add interactive testing where possible
4. Update this README with new examples
5. Ensure examples run on Python 3.12+

## Common Patterns

### Request-Scoped Cancelation (Web APIs)

```python
from hother.cancelable.integrations.fastapi import cancelable_dependency

@app.get("/api/data")
async def get_data(cancel: Cancelable = Depends(cancelable_dependency)):
    async with cancel:
        return await fetch_data_with_cancelation()
```

### Stream Processing with Cancelation

```python
from hother.cancelable import cancelable_stream

async with Cancelable.with_timeout(30.0) as cancel:
    async for item in cancelable_stream(data_stream, cancel):
        await process_item(item)
```

## Troubleshooting

### Common Issues

1. **"CancelScope not properly closed"**: Ensure proper async context manager usage
2. **Signal handlers not working**: Check signal availability on your platform
3. **Import errors**: Ensure `hother-cancelable` is installed: `uv add hother-cancelable`

### Platform Notes

- Signal handling works on Unix-like systems (Linux, macOS)
- Windows has limited signal support (primarily SIGINT)
- Some examples require multiple terminals for full testing

## Related Documentation

- [Main Documentation](../docs/)
- [API Reference](../docs/api_reference/)
- [Integration Guides](../docs/integrations/)