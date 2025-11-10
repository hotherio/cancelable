# Examples

Complete, runnable examples demonstrating Cancelable in real-world scenarios.

## Browse by Category

All examples are **complete and runnable**. You can copy-paste them directly or find the source in the [`examples/`](https://github.com/hotherio/cancelable/tree/main/examples) directory.

### [Basic Patterns](basic.md)

Learn fundamental cancelation patterns:

- ⏱️ **Timeout Cancelation** - Simple time-based cancelation
- ✋ **Manual Cancelation** - User-initiated cancelation with tokens
- 🔔 **Signal Handling** - OS signal-based graceful shutdown
- 🎯 **Condition-Based** - Cancel based on custom logic
- 🔗 **Combined Sources** - Compose multiple cancelation triggers

**Best for:** Getting started, understanding core concepts

### [Stream Processing](streams.md)

Handle async streams with cancelation:

- 📊 **Buffered Streams** - Process data with backpressure
- ⏸️ **Cancelable Iteration** - Stop stream processing cleanly
- 🔄 **Transform & Filter** - Streaming transformations with cancelation
- 📈 **Progress Tracking** - Report stream processing progress

**Best for:** Data pipelines, ETL, real-time processing

### [Web Applications](web.md)

Integrate with web frameworks:

- 🚀 **FastAPI Request Scoped** - Automatic cancelation on disconnect
- 📡 **Background Tasks** - Long-running tasks with manual cancel
- 🔌 **WebSocket Streams** - Real-time data with cancelation
- ⏲️ **API Timeouts** - Request-level timeout handling

**Best for:** Web APIs, REST services, real-time applications

### [Monitoring Dashboard](monitoring.md)

Build observability and monitoring:

- 📊 **Real-time Dashboard** - Monitor all active operations
- 📈 **Progress Visualization** - Display operation progress
- ⚠️ **Alert System** - Detect stuck or failing operations
- 📉 **Metrics Export** - Send to Prometheus, Datadog, etc.

**Best for:** Production monitoring, debugging, observability

### [LLM Integration](llm.md)

Integrate with Large Language Models:

- 🤖 **LLM Streaming** - Stream AI responses with cancelation
- ⏸️ **User Pause/Resume** - Keyboard-based pause control
- 🎯 **LLM-Initiated Pause** - AI signals when to pause
- 📝 **Context Preservation** - Resume from exact position

**Best for:** AI applications, chatbots, content generation

## Quick Start Examples

### Simple Timeout

```python
from hother.cancelable import Cancelable
import anyio

async def main():
    async with Cancelable.with_timeout(30.0) as cancel:
        await long_operation()

anyio.run(main)
```

### Manual Cancelation

```python
from hother.cancelable import CancelationToken

token = CancelationToken()

async def worker():
    async with Cancelable.with_token(token) as cancel:
        await task()

async def controller():
    await anyio.sleep(5)
    await token.cancel("User stopped")

async with anyio.create_task_group() as tg:
    tg.start_soon(worker)
    tg.start_soon(controller)
```

### Combined Cancelation

```python
import signal
from hother.cancelable import TimeoutSource, SignalSource

async with Cancelable.combine([
    TimeoutSource(60.0),
    SignalSource(signal.SIGTERM),
    manual_token
]) as cancel:
    await operation()  # Cancels on FIRST trigger
```

## Running Examples

All examples in the [`examples/`](https://github.com/hotherio/cancelable/tree/main/examples) directory can be run directly:

```bash
# Basic examples
python examples/01_basics/01_basic_cancelation.py
python examples/01_basics/02_timeout_cancelation.py

# Advanced patterns
python examples/02_advanced/01_combined_cancelation.py

# Monitoring dashboard
python examples/05_monitoring/01_monitoring_dashboard.py

# LLM streaming (requires API key)
GEMINI_API_KEY="your-key" python examples/06_llm/01_llm_streaming.py
```

## Example Structure

Each example includes:

- **Complete, runnable code** - Copy-paste ready
- **Clear documentation** - Explains what and why
- **Expected output** - What you should see
- **Variations** - Different approaches to try
- **Best practices** - Production-ready patterns

## By Use Case

Not sure which example to use? Find your scenario:

| What You're Building | Recommended Example |
|---------------------|---------------------|
| Web API endpoint | [FastAPI Request Scoped](web.md) |
| Data processing pipeline | [Stream Processing](streams.md) |
| Background job system | [Web Background Tasks](web.md) |
| AI chatbot | [LLM Streaming](llm.md) |
| Monitoring dashboard | [Real-time Dashboard](monitoring.md) |
| CLI tool with Ctrl+C | [Signal Handling](basic.md) |
| Long-running export | [Progress Tracking](streams.md) |

## Contributing Examples

Have a useful pattern? [Submit an example!](https://github.com/hotherio/cancelable/issues)

## Next Steps

- **[Basic Patterns](basic.md)** - Start here if you're new
- **[Core Concepts](../basics.md)** - Understand the fundamentals
- **[Integrations](../integrations/index.md)** - Framework-specific guides
- **[Advanced Patterns](../patterns.md)** - Production patterns
