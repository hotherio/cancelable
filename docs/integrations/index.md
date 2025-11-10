# Integrations

Framework-specific guides for integrating Cancelable.

## Available Integrations

Cancelable provides first-class integration with popular async frameworks:

### [FastAPI](fastapi.md)

Web framework integration with request-scoped cancelation.

**Features:**

- Automatic cancelation on client disconnect
- Request-scoped operation tracking
- Dependency injection support
- Background task management

**Quick Example:**

```python
from fastapi import FastAPI, Depends
from hother.cancelable.integrations.fastapi import cancelable_dependency

app = FastAPI()

@app.get("/process")
async def process(cancel: Cancelable = Depends(cancelable_dependency)):
    async with cancel:
        return await heavy_computation()
```

[Read FastAPI Guide →](fastapi.md)

## Future Integrations

Planning to add:

- Django (async views)
- Starlette
- aiohttp
- Redis (aioredis)
- Celery

Want to see an integration? [Open an issue!](https://github.com/hotherio/cancelable/issues)

## Next Steps

- Explore [FastAPI Integration](fastapi.md) - Web APIs
- Browse [Examples](../examples/index.md) - Integration examples
