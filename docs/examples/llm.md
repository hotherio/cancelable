# LLM Integration Examples

Integrate Cancelable with Large Language Model streaming operations.

_Find the complete source in [`examples/06_llm/`](https://github.com/hotherio/cancelable/tree/main/examples/06_llm)._

## LLM Streaming with Pause/Resume

Stream AI responses with user and AI-initiated cancelation.

### Features

- **Keyboard Control** - Press SPACE to pause/resume streaming
- **LLM-Initiated Pause** - AI signals when to pause with special markers
- **Context Preservation** - Resume from exact position
- **CancelationToken Integration** - Clean cancelation handling

### Example

```python
from hother.cancelable import CancelationToken

token = CancelationToken()

async def stream_llm():
    async with Cancelable.with_token(token) as cancel:
        async for chunk in llm_client.stream(prompt):
            # Check for pause markers
            if '!!CANCEL' in chunk:
                token.cancel_sync(message="LLM initiated pause")
                break

            print(chunk, end='', flush=True)
```

**Run it:**
```bash
GEMINI_API_KEY="your-key" python examples/06_llm/01_llm_streaming.py
```

### Use Cases

- **Interactive Tutorials** - LLM pauses for user to try examples
- **Content Generation** - User controls output generation
- **Cost Control** - Stop expensive API calls
- **Reasoning Steps** - AI pauses between thinking steps

## Requirements

```bash
pip install google-genai pynput  # For Google GenAI example
```

## Next Steps

- Review [Basic Patterns](basic.md) - Fundamental cancelation
- Explore [Web Applications](web.md) - API integration
- See [Stream Processing](streams.md) - Async stream handling
